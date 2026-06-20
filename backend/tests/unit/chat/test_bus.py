"""Unit tests for ConversationBus — per-conversation event fan-out + replay (ADR-031)."""

from __future__ import annotations

import asyncio
from typing import Any

from coffer.application.chat.bus import ConversationBus
from coffer.domain.chat.events import AgentEvent, QueueChanged, TextDelta, TurnStarted


def _drain(q: asyncio.Queue[Any]) -> list[Any]:
    out: list[Any] = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_publish_fans_out_to_all_subscribers() -> None:
    bus = ConversationBus()
    a = bus.subscribe()
    b = bus.subscribe()
    bus.begin_turn()
    ev: AgentEvent = TextDelta(text="hi")
    bus.publish(ev)
    assert _drain(a) == [ev]
    assert _drain(b) == [ev]


def test_late_subscriber_replays_current_turn_buffer() -> None:
    bus = ConversationBus()
    bus.begin_turn()
    e1: AgentEvent = TurnStarted()
    e2: AgentEvent = TextDelta(text="he")
    bus.publish(e1)
    bus.publish(e2)
    late = bus.subscribe()
    # A subscriber that attaches mid-turn catches up on what already streamed.
    assert _drain(late) == [e1, e2]


def test_end_turn_clears_replay_buffer() -> None:
    bus = ConversationBus()
    bus.begin_turn()
    bus.publish(TextDelta(text="x"))
    bus.end_turn()
    late = bus.subscribe()
    # A completed turn is loaded from history, not replayed from the buffer.
    assert _drain(late) == []


def test_queue_changed_replayed_to_new_subscriber() -> None:
    bus = ConversationBus()
    qc: AgentEvent = QueueChanged(pending=["a", "b"])
    bus.publish_queue_changed(qc)
    late = bus.subscribe()
    assert _drain(late) == [qc]


def test_queue_snapshot_survives_begin_turn() -> None:
    bus = ConversationBus()
    qc: AgentEvent = QueueChanged(pending=["a"])
    bus.publish_queue_changed(qc)
    bus.begin_turn()
    late = bus.subscribe()
    assert _drain(late) == [qc]


def test_unsubscribe_stops_delivery() -> None:
    bus = ConversationBus()
    a = bus.subscribe()
    bus.unsubscribe(a)
    bus.begin_turn()
    bus.publish(TextDelta(text="x"))
    assert _drain(a) == []


def test_close_sends_sentinel_and_clears_subscribers() -> None:
    bus = ConversationBus()
    a = bus.subscribe()
    bus.close()
    assert _drain(a) == [None]
    assert bus.subscriber_count == 0
