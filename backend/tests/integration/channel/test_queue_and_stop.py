"""Mid-turn behavior: /new, /stop, the bounded in-order queue, and overflow.

A gated scripted agent holds turns open on an asyncio.Event so the tests
control exactly when each turn starts and finishes — no sleeps.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from coffer.application.channel.turn_driver import DROPPED_NOTICE, queued_notice
from coffer.application.chat.turn_orchestrator import active_turns
from coffer.domain.channel.envelopes import InboundStop
from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    TurnDone,
    TurnStarted,
)

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, turn_body, uid_of, wait_until


class GatedAdapter:
    """Scripted agent whose turns block on ``release``; records run order."""

    model_id = None

    def __init__(self) -> None:
        self.entered = asyncio.Event()  # set when the first event streams
        self.release = asyncio.Event()
        self.runs: list[str] = []

    async def run_turn(self, prompt: str, attachments: object = ()) -> AsyncIterator[AgentEvent]:
        text = turn_body(prompt)

        async def gen() -> AsyncIterator[AgentEvent]:
            self.runs.append(text)
            self.entered.set()
            yield TurnStarted()
            await self.release.wait()
            yield TextDelta(text=f"echo:{text}")
            yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")

        return gen()


@pytest.mark.acceptance(spec="channels", scenario="/new starts a fresh conversation")
async def test_new_command_switches_to_a_fresh_conversation(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    old_conversation = await env.active_conversation(resource)
    assert old_conversation is not None

    await env.processor.on_message(inbound("tg", "owner", "/new"))

    assert "🆕 New conversation · Coffer Assistant · Default model · Default directory" in (
        adapter.texts()
    )
    fresh = await env.active_conversation(resource)
    assert fresh is not None
    assert fresh != old_conversation
    listed = [c.id for c in await env.conversations()]
    assert old_conversation in listed  # the old thread stays in history
    assert fresh in listed


async def test_stopping_is_edited_into_the_result_where_the_platform_can_edit(
    env: ChannelEnv,
) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(edits_text=True, supports_card_update=True))
    await env.pair(resource, "owner")

    await env.processor.on_message(inbound("tg", "owner", "long job"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    await env.processor.on_message(inbound("tg", "owner", "/stop"))

    await wait_until(lambda: bool(adapter.card_updates))
    [(_chat, _mid, text, buttons, _title)] = adapter.card_updates
    assert text.startswith("⏹ Stopped “long job” after ")
    assert buttons == []
    # One message, rewritten: no second "Stopped" message follows the first.
    assert not any(t.startswith("⏹ Stopped") for t in adapter.texts())


@pytest.mark.acceptance(spec="channels", scenario="/stop with no turn in flight says so")
async def test_stop_after_the_reply_says_nothing_is_running(env: ChannelEnv) -> None:
    # The chat still has its conversation bound, but its turn has finished:
    # there is nothing to stop, and a "Stopping…" would never be resolved.
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    assert await env.active_conversation(resource) is not None
    await wait_until(lambda: not active_turns())

    await env.processor.on_message(inbound("tg", "owner", "/stop"))

    assert adapter.texts()[-1] == "Nothing is running."
    assert "⏹ Stopping…" not in adapter.texts()


@pytest.mark.acceptance(spec="channels", scenario="/stop interrupts a running turn")
async def test_stop_command_interrupts_the_running_turn(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "long job"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    assert conversation_id in active_turns()

    await env.processor.on_message(inbound("tg", "owner", "/stop"))

    assert "⏹ Stopping “long job”…" in adapter.texts()
    # The interrupted turn ends and the renderer reports the stop.
    await wait_until(lambda: any(t.startswith("⏹ Stopped") for t in adapter.texts()))
    # The orchestrator slot is freed — the chat is responsive again.
    await wait_until(lambda: conversation_id not in active_turns())
    # No echo was produced: the turn never reached its reply.
    assert not any(t.startswith("echo:") for t in adapter.texts())


async def test_stop_after_new_interrupts_the_still_draining_turn(env: ChannelEnv) -> None:
    # A turn is running on conversation A; /new rebinds the peer to a fresh
    # conversation B while A is still draining. /stop must interrupt the turn
    # that is actually running (A), not the idle bound conversation (B) — and
    # it must not falsely claim "Stopping…" against B.
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "long job"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    running_conversation = await env.active_conversation(resource)
    assert running_conversation is not None
    assert running_conversation in active_turns()

    await env.processor.on_message(inbound("tg", "owner", "/new"))
    fresh_conversation = await env.active_conversation(resource)
    assert fresh_conversation is not None
    assert fresh_conversation != running_conversation
    # The fresh conversation has no turn — interrupting it would be a no-op.
    assert fresh_conversation not in active_turns()
    assert running_conversation in active_turns()

    await env.processor.on_message(inbound("tg", "owner", "/stop"))

    assert "⏹ Stopping “long job”…" in adapter.texts()
    # The turn that was actually running is the one that gets stopped.
    await wait_until(lambda: running_conversation not in active_turns())
    assert not any(t.startswith("echo:") for t in adapter.texts())


async def test_unbind_mid_turn_interrupts_the_draining_turn(env: ChannelEnv) -> None:
    # A config disable / shutdown unbinds the channel mid-turn. Cancelling only
    # the renderer leaves the orchestrator turn running: its reply lands in the
    # web UI while the bot goes silent. Unbind must interrupt the live turn.
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, _adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "long job"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    running_conversation = await env.active_conversation(resource)
    assert running_conversation is not None
    assert running_conversation in active_turns()

    env.processor.unbind(resource.uid)

    # The live turn is interrupted instead of completing undelivered.
    await wait_until(lambda: running_conversation not in active_turns())


@pytest.mark.acceptance(spec="channels", scenario="messages during a turn are queued in order")
async def test_messages_sent_mid_turn_run_as_consecutive_turns_in_order(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "A"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    # Each message is released before the next arrives: this is about the
    # queue behind a running turn, not about a burst merging into one.
    await env.send(inbound("tg", "owner", "B"))
    await env.send(inbound("tg", "owner", "C"))

    gated.release.set()
    await wait_until(lambda: "echo:C" in adapter.texts())

    assert gated.runs == ["A", "B", "C"]
    assert [t for t in adapter.texts() if t.startswith("echo:")] == [
        "echo:A",
        "echo:B",
        "echo:C",
    ]
    # All three turns landed in the thread's single conversation, in order.
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    assert env.user_texts(conversation_id) == ["A", "B", "C"]


@pytest.mark.acceptance(spec="channels", scenario="the queue is bounded and overflow is reported")
async def test_eleventh_queued_message_is_dropped_with_the_reason(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    _resource, adapter = await env.paired_channel()

    await env.send(inbound("tg", "owner", "m0"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    queued = [f"q{i}" for i in range(1, 11)]
    for text in queued:  # fill the queue to its bound of 10
        await env.send(inbound("tg", "owner", text))
    # Each waiting message is told its place in the queue, and none is dropped.
    notices = [t for t in adapter.texts() if t.startswith("⏳ Queued")]
    assert notices == [queued_notice() for _ in range(10)]
    assert DROPPED_NOTICE not in adapter.texts()

    await env.send(inbound("tg", "owner", "overflow"))
    assert DROPPED_NOTICE in adapter.texts()
    assert "10 messages are already waiting" in DROPPED_NOTICE

    gated.release.set()
    await wait_until(lambda: "echo:q10" in adapter.texts(), timeout=10.0)

    # Every queued message ran; the overflowing one never did.
    assert gated.runs == ["m0", *queued]
    assert "overflow" not in gated.runs
    assert "echo:overflow" not in adapter.texts()


@pytest.mark.acceptance(
    spec="chat", scenario="a channel message waits in the conversation's own queue"
)
async def test_channel_messages_queued_mid_turn_ride_the_conversation_queue(
    env: ChannelEnv,
) -> None:
    # spec chat "Queue messages sent during a turn": the channel keeps no queue of
    # its own. A message sent from the phone while a turn runs waits on the SAME
    # pending queue a web send would, so the web's pending chips show it and both
    # surfaces drain one FIFO.
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await env.paired_channel()

    await env.send(inbound("tg", "owner", "A"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    await env.send(inbound("tg", "owner", "B"))
    await env.orchestrator.enqueue_message(conversation_id, "C from the side")
    await env.send(inbound("tg", "owner", "D"))

    pending = env.orchestrator.pending(conversation_id)
    assert [turn_body(t) for t in pending] == ["B", "C from the side", "D"]

    gated.release.set()
    await wait_until(lambda: "echo:D" in adapter.texts())
    assert gated.runs == ["A", "B", "C from the side", "D"]
    # The side send ran in its slot but was not the channel's to render.
    assert [t for t in adapter.texts() if t.startswith("echo:")] == ["echo:A", "echo:B", "echo:D"]
    assert env.orchestrator.pending(conversation_id) == []


@pytest.mark.acceptance(spec="chat", scenario="a stop from the chat holds the queued messages")
async def test_stop_holds_the_queued_messages_until_the_next_message(env: ChannelEnv) -> None:
    # spec chat "Pause the pending queue on interrupt" reaches the channel too:
    # /stop pauses the queue rather than letting the next message fire into the turn
    # just stopped; the next send resumes it.
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await env.paired_channel()

    await env.send(inbound("tg", "owner", "A"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    await env.send(inbound("tg", "owner", "B"))

    await env.send(inbound("tg", "owner", "/stop"))
    await wait_until(lambda: any(t.startswith("⏹ Stopped") for t in adapter.texts()))
    # The stop names what it stopped, and the message queued behind it waits.
    [stopped] = [t for t in adapter.texts() if t.startswith("⏹ Stopped")]
    assert stopped.startswith("⏹ Stopped “A” after ")
    assert stopped.endswith("⏸ 1 queued message is on hold — send anything to continue.")
    await wait_until(lambda: conversation_id not in active_turns())
    await asyncio.sleep(0.05)
    assert [turn_body(t) for t in env.orchestrator.pending(conversation_id)] == ["B"]
    assert gated.runs == ["A"]  # B is held, not run

    gated.release.set()
    await env.send(inbound("tg", "owner", "C"))
    await wait_until(lambda: "echo:C" in adapter.texts())
    assert gated.runs == ["A", "B", "C"]


# -- the platform's own stop control ------------------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="a stop pressed on the platform's own control ends the turn"
)
async def test_platform_stop_control_interrupts_like_a_typed_stop(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "long job"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    conversation_id = await env.active_conversation(resource)
    assert conversation_id is not None
    assert conversation_id in active_turns()
    await env.send(inbound("tg", "owner", "queued behind it"))

    # The user presses the button Telegram drew on the streamed draft.
    await env.processor.on_stop(InboundStop(channel=uid_of("tg"), chat_id="owner"))

    assert "⏹ Stopping “long job”…" in adapter.texts()
    await wait_until(lambda: any(t.startswith("⏹ Stopped") for t in adapter.texts()))
    await wait_until(lambda: conversation_id not in active_turns())
    assert not any(t.startswith("echo:") for t in adapter.texts())
    # Like a typed /stop it pauses the queue: the waiting message is held, not run.
    await asyncio.sleep(0.05)
    assert [turn_body(t) for t in env.orchestrator.pending(conversation_id)] == ["queued behind it"]
    assert gated.runs == ["long job"]


async def test_platform_stop_with_nothing_running_says_so(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel()

    await env.processor.on_stop(InboundStop(channel=uid_of("tg"), chat_id="owner"))

    assert "Nothing is running." in adapter.texts()


async def test_platform_stop_from_an_unpaired_chat_is_ignored(env: ChannelEnv) -> None:
    # Answering would confirm to a stranger that this channel exists.
    _resource, adapter = await env.paired_channel(chat_id="owner")

    await env.processor.on_stop(InboundStop(channel=uid_of("tg"), chat_id="stranger"))

    assert adapter.sent == []


async def test_platform_stop_in_a_thread_answers_in_that_thread(env: ChannelEnv) -> None:
    _resource, adapter = await env.paired_channel(chat_id="-100group")

    await env.processor.on_stop(
        InboundStop(channel=uid_of("tg"), chat_id="-100group", thread_id="8", chat_kind="group")
    )

    assert ("-100group", "Nothing is running.", "8", "group") in adapter.sent_routed


async def test_status_while_a_turn_runs_counts_the_waiting_and_offers_stop(
    env: ChannelEnv,
) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    await env.pair(resource, "owner")

    await env.send(inbound("tg", "owner", "A"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    await env.send(inbound("tg", "owner", "B"))
    await env.processor.on_message(inbound("tg", "owner", "/status"))

    _chat, text, buttons = adapter.cards[-1]
    assert text.splitlines()[2] == "Running · 1 waiting"
    assert [b.label for b in buttons] == ["Stop", "New", "Model", "Resume", "Dir"]
    gated.release.set()
