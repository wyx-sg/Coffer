"""EventBroker: numbering, the bounded replay buffer, resync, and overflow."""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.events.broker import Envelope, EventBroker, Resync, Subscription
from coffer.domain.reconcile import Changed


async def _drain(sub: Subscription) -> list[Envelope | Resync]:
    out: list[Envelope | Resync] = []
    while sub.pending():
        item = await sub.next(timeout=0)
        assert item is not None
        out.append(item)
    return out


def _publish(broker: EventBroker, n: int) -> None:
    for i in range(n):
        broker.publish("skill", f"u{i}", i + 1)


def test_seq_starts_at_one_and_grows_by_one_per_envelope() -> None:
    broker = EventBroker()
    assert broker.head == 0
    first = broker.publish("skill", "u1", 3)
    second = broker.publish("agent", "u2", 1, "delete")
    assert first == Envelope(1, "skill", "u1", 3, "upsert")
    assert second == Envelope(2, "agent", "u2", 1, "delete")
    assert broker.head == 2


def test_a_changed_hint_becomes_an_envelope_with_its_op() -> None:
    broker = EventBroker()
    broker.publish_changed(Changed("mcp_server", "u9", 4))
    broker.publish_changed(Changed("mcp_server", "u9", 5, "delete"))
    assert broker.buffered == (
        Envelope(1, "mcp_server", "u9", 4, "upsert"),
        Envelope(2, "mcp_server", "u9", 5, "delete"),
    )


def test_the_buffer_keeps_only_the_latest_envelopes() -> None:
    broker = EventBroker(buffer_size=3)
    _publish(broker, 5)
    assert [e.seq for e in broker.buffered] == [3, 4, 5]


async def test_a_live_subscriber_receives_what_is_published_after_it() -> None:
    broker = EventBroker()
    _publish(broker, 2)
    sub = broker.subscribe()
    broker.publish("skill", "later", 1)
    assert await _drain(sub) == [Envelope(3, "skill", "later", 1, "upsert")]


async def test_resuming_replays_exactly_the_envelopes_after_the_last_seen() -> None:
    broker = EventBroker()
    _publish(broker, 5)
    sub = broker.subscribe(last_event_id=3)
    assert [i.seq for i in await _drain(sub) if isinstance(i, Envelope)] == [4, 5]
    broker.publish("skill", "live", 1)
    assert await _drain(sub) == [Envelope(6, "skill", "live", 1, "upsert")]


async def test_resuming_at_the_head_or_just_before_the_oldest_needs_no_resync() -> None:
    broker = EventBroker(buffer_size=3)
    _publish(broker, 5)  # buffer holds 3..5
    assert await _drain(broker.subscribe(last_event_id=5)) == []
    assert [i.seq for i in await _drain(broker.subscribe(last_event_id=2))] == [3, 4, 5]


@pytest.mark.parametrize("last_seen", [1, 0])
async def test_a_gap_older_than_the_buffer_is_one_resync(last_seen: int) -> None:
    broker = EventBroker(buffer_size=3)
    _publish(broker, 5)  # buffer holds 3..5; 1 and 2 are gone
    assert await _drain(broker.subscribe(last_event_id=last_seen)) == [Resync(5)]


@pytest.mark.parametrize("foreign", [99, -1])
async def test_an_id_this_run_never_issued_is_one_resync(foreign: int) -> None:
    broker = EventBroker()
    _publish(broker, 2)
    sub = broker.subscribe(last_event_id=foreign)
    assert await _drain(sub) == [Resync(2)]
    broker.publish("skill", "live", 1)
    assert await _drain(sub) == [Envelope(3, "skill", "live", 1, "upsert")]


async def test_resuming_from_zero_on_a_fresh_run_replays_everything() -> None:
    broker = EventBroker()
    _publish(broker, 2)
    assert [i.seq for i in await _drain(broker.subscribe(last_event_id=0))] == [1, 2]


async def test_a_subscriber_that_falls_behind_is_resynced_then_carries_on_live() -> None:
    broker = EventBroker(queue_size=2)
    sub = broker.subscribe()
    _publish(broker, 3)  # the third overflows the queue of two
    assert await _drain(sub) == [Resync(3)]
    broker.publish("skill", "live", 1)
    assert await _drain(sub) == [Envelope(4, "skill", "live", 1, "upsert")]


async def test_an_overflowing_subscriber_never_holds_more_than_its_limit() -> None:
    broker = EventBroker(queue_size=4)
    sub = broker.subscribe()
    _publish(broker, 100)
    assert sub.pending() <= 4
    items = await _drain(sub)
    assert isinstance(items[0], Resync)


async def test_next_waits_for_a_publish_and_times_out_when_idle() -> None:
    broker = EventBroker()
    sub = broker.subscribe()
    assert await sub.next(timeout=0.01) is None
    waiter = asyncio.ensure_future(sub.next(timeout=1))
    await asyncio.sleep(0)
    broker.publish("skill", "u1", 1)
    assert await waiter == Envelope(1, "skill", "u1", 1, "upsert")


def test_a_closed_subscription_receives_nothing_more() -> None:
    broker = EventBroker()
    sub = broker.subscribe()
    assert broker.subscriber_count == 1
    sub.close()
    sub.close()  # idempotent
    broker.publish("skill", "u1", 1)
    assert broker.subscriber_count == 0
    assert sub.pending() == 0


def test_sizes_must_be_positive() -> None:
    with pytest.raises(ValueError):
        EventBroker(buffer_size=0)
    with pytest.raises(ValueError):
        EventBroker(queue_size=0)
