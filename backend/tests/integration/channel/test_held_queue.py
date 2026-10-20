"""Continue or Discard the messages a `/stop` held (spec channels "Continue or
discard the messages a stop held", and spec chat "Pause the pending queue on
interrupt")."""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.chat.turn_orchestrator import active_turns

from .conftest import (
    ChannelEnv,
    FakeChannelAdapter,
    inbound,
    tap_event,
    turn_body,
    wait_until,
)
from .test_queue_and_stop import GatedAdapter

HELD_LINE = "⏸ 1 queued message is on hold."


async def _stopped_with_one_held(
    env: ChannelEnv, adapter: FakeChannelAdapter
) -> tuple[GatedAdapter, str]:
    """``A`` running, ``B`` queued behind it, then `/stop`: ``B`` is held."""
    gated = GatedAdapter()
    env.provider.adapter = gated
    await env.send(inbound("tg", "owner", "A"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    conversation_id = next(iter(active_turns()))
    await env.send(inbound("tg", "owner", "B"))
    await env.send(inbound("tg", "owner", "/stop"))
    await wait_until(lambda: conversation_id not in active_turns())
    await wait_until(lambda: any(text == HELD_LINE for _chat, text, _b in adapter.cards))
    return gated, conversation_id


async def _button_channel(env: ChannelEnv) -> FakeChannelAdapter:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    await env.pair(resource, "owner")
    return adapter


def _held_card(adapter: FakeChannelAdapter) -> list[str]:
    [buttons] = [b for _chat, text, b in adapter.cards if text == HELD_LINE]
    return [b.value for b in buttons]


@pytest.mark.acceptance(
    spec="channels", scenario="a stop that holds messages offers Continue and Discard"
)
async def test_a_stop_that_holds_messages_offers_continue_and_discard(env: ChannelEnv) -> None:
    adapter = await _button_channel(env)
    _gated, conversation_id = await _stopped_with_one_held(env, adapter)

    # The stopped line says what stopped; the held line rides its own card.
    [stopped] = [t for t in adapter.texts() if t.startswith("⏹ Stopped")]
    assert "on hold" not in stopped
    assert _held_card(adapter) == [f"held:go:{conversation_id}", f"held:drop:{conversation_id}"]


async def test_the_stopped_line_carries_the_buttons_where_it_is_edited(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource,
        FakeChannelAdapter(supports_buttons=True, edits_text=True, supports_card_update=True),
    )
    await env.pair(resource, "owner")
    gated = GatedAdapter()
    env.provider.adapter = gated
    await env.send(inbound("tg", "owner", "A"))
    await asyncio.wait_for(gated.entered.wait(), timeout=5.0)
    conversation_id = next(iter(active_turns()))
    await env.send(inbound("tg", "owner", "B"))
    await env.send(inbound("tg", "owner", "/stop"))

    await wait_until(lambda: bool(adapter.card_updates))
    [(_chat, _mid, text, buttons, _title)] = adapter.card_updates
    assert text.endswith("\n" + HELD_LINE)
    assert [b.label for b in buttons] == ["▶ Continue", "Discard"]
    assert buttons[0].value == f"held:go:{conversation_id}"


@pytest.mark.acceptance(spec="channels", scenario="Continue runs the held messages in order")
async def test_continue_runs_the_held_messages(env: ChannelEnv) -> None:
    adapter = await _button_channel(env)
    gated, conversation_id = await _stopped_with_one_held(env, adapter)
    gated.release.set()

    await env.processor.on_callback(tap_event("tg", "owner", f"held:go:{conversation_id}"))

    assert "▶ Continuing 1 queued message." in adapter.texts()
    await wait_until(lambda: gated.runs == ["A", "B"])
    # Settled: a second tap finds nothing left to hold.
    await wait_until(lambda: not env.orchestrator.pending(conversation_id))
    await env.processor.on_callback(tap_event("tg", "owner", f"held:drop:{conversation_id}"))
    assert adapter.texts()[-1] == "Nothing is on hold any more."


@pytest.mark.acceptance(spec="channels", scenario="Discard drops the held messages")
async def test_discard_drops_the_held_messages(env: ChannelEnv) -> None:
    adapter = await _button_channel(env)
    gated, conversation_id = await _stopped_with_one_held(env, adapter)
    gated.release.set()

    await env.processor.on_callback(tap_event("tg", "owner", f"held:drop:{conversation_id}"))

    assert adapter.texts()[-1] == "🗑 Discarded 1 queued message."
    assert env.orchestrator.pending(conversation_id) == []
    # What is sent next runs on its own; the discarded message never does.
    await env.send(inbound("tg", "owner", "C"))
    await wait_until(lambda: gated.runs == ["A", "C"])


async def test_a_tap_for_another_chats_conversation_does_nothing(env: ChannelEnv) -> None:
    adapter = await _button_channel(env)
    _gated, conversation_id = await _stopped_with_one_held(env, adapter)

    await env.processor.on_callback(tap_event("tg", "owner", "held:drop:not-this-chats"))

    assert adapter.texts()[-1] == "Nothing is on hold any more."
    assert [turn_body(t) for t in env.orchestrator.pending(conversation_id)] == ["B"]


@pytest.mark.acceptance(spec="channels", scenario="/status counts the messages a stop held")
async def test_status_counts_the_held_messages_and_offers_to_settle_them(
    env: ChannelEnv,
) -> None:
    adapter = await _button_channel(env)
    _gated, conversation_id = await _stopped_with_one_held(env, adapter)

    await env.processor.on_message(inbound("tg", "owner", "/status"))

    _chat, text, buttons = adapter.cards[-1]
    assert text.splitlines()[2] == "⏸ 1 on hold"
    assert [b.label for b in buttons] == ["▶ Continue", "Discard", "Model", "Dir"]
    assert buttons[1].value == f"held:drop:{conversation_id}"
