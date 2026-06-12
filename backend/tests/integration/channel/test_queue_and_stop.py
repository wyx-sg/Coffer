"""Mid-turn behavior: /new, /stop, the bounded in-order queue, and overflow.

A gated scripted agent holds turns open on an asyncio.Event so the tests
control exactly when each turn starts and finishes — no sleeps.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from coffer.application.chat.turn_orchestrator import active_turns
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import Message, Role, TextBlock

from .conftest import ChannelEnv, inbound, wait_until


class GatedAdapter:
    """Scripted agent whose turns block on ``release``; records run order."""

    model_id = None

    def __init__(self) -> None:
        self.entered = asyncio.Event()  # set when the first event streams
        self.release = asyncio.Event()
        self.runs: list[str] = []

    async def run_turn(
        self, *, history: Sequence[Message], approvals: Any
    ) -> AsyncIterator[AgentEvent]:
        last = history[-1]
        text = "".join(b.text for b in last.content if isinstance(b, TextBlock))

        async def gen() -> AsyncIterator[AgentEvent]:
            self.runs.append(text)
            self.entered.set()
            yield TurnStarted()
            await self.release.wait()
            yield TextDelta(text=f"echo:{text}")
            yield TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")

        return gen()


@pytest.mark.acceptance(spec="009-channels", scenario="/new starts a fresh conversation")
async def test_new_command_switches_to_a_fresh_conversation(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    peer = await env.peers.get(resource.id)
    assert peer is not None
    old_conversation = peer.active_conversation_id
    assert old_conversation is not None

    await env.processor.on_message(inbound("tg", "owner", "/new"))

    assert "🆕 Started a fresh conversation." in adapter.texts()
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.active_conversation_id is not None
    assert peer.active_conversation_id != old_conversation
    listed = [c.id for c in await env.chat.list_conversations()]
    assert old_conversation in listed  # the old thread stays in history
    assert peer.active_conversation_id in listed


@pytest.mark.acceptance(spec="009-channels", scenario="/stop interrupts a running turn")
async def test_stop_command_interrupts_the_running_turn(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "long job"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    peer = await env.peers.get(resource.id)
    assert peer is not None
    conversation_id = peer.active_conversation_id
    assert conversation_id is not None
    assert conversation_id in active_turns()

    await env.processor.on_message(inbound("tg", "owner", "/stop"))

    assert "⏹ Stopping…" in adapter.texts()
    # The interrupted turn ends and the renderer reports the stop.
    await wait_until(lambda: "⏹ Stopped." in adapter.texts())
    # The orchestrator slot is freed — the chat is responsive again.
    await wait_until(lambda: conversation_id not in active_turns())
    # No echo was produced: the turn never reached its reply.
    assert not any(t.startswith("echo:") for t in adapter.texts())


@pytest.mark.acceptance(spec="009-channels", scenario="messages during a turn are queued in order")
async def test_messages_sent_mid_turn_run_as_consecutive_turns_in_order(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "A"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    await env.processor.on_message(inbound("tg", "owner", "B"))
    await env.processor.on_message(inbound("tg", "owner", "C"))

    gated.release.set()
    await wait_until(lambda: "echo:C" in adapter.texts())

    assert gated.runs == ["A", "B", "C"]
    assert [t for t in adapter.texts() if t.startswith("echo:")] == [
        "echo:A",
        "echo:B",
        "echo:C",
    ]
    # All three turns landed in the peer's single conversation, in order.
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.active_conversation_id is not None
    messages = await env.chat.list_messages(peer.active_conversation_id)
    user_texts = [
        "".join(b.text for b in m.content if isinstance(b, TextBlock))
        for m in messages
        if m.role == Role.USER
    ]
    assert user_texts == ["A", "B", "C"]
    assert len(messages) == 6  # user/assistant interleaved


@pytest.mark.acceptance(
    spec="009-channels", scenario="the queue is bounded and overflow is reported"
)
async def test_eleventh_queued_message_is_dropped_with_a_busy_notice(env: ChannelEnv) -> None:
    gated = GatedAdapter()
    env.provider.adapter = gated
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "m0"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    queued = [f"q{i}" for i in range(1, 11)]
    for text in queued:  # fill the queue to its bound of 10
        await env.processor.on_message(inbound("tg", "owner", text))
    assert "⚠️ Busy — message dropped, try again." not in adapter.texts()

    await env.processor.on_message(inbound("tg", "owner", "overflow"))
    assert "⚠️ Busy — message dropped, try again." in adapter.texts()

    gated.release.set()
    await wait_until(lambda: "echo:q10" in adapter.texts(), timeout=10.0)

    # Every queued message ran; the overflowing one never did.
    assert gated.runs == ["m0", *queued]
    assert "overflow" not in gated.runs
    assert "echo:overflow" not in adapter.texts()
