"""Unit tests for `coffer.application.memory.aggregate_worker.AggregateWorker`.

FR-007's two halves: aggregation runs unattended on an interval, and a pass
that fails does not end the loop. No filesystem, no database — the worker is
a loop around one injected callable, and that is all these assert.
"""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.memory.aggregate_worker import WORKER_ACTOR, AggregateWorker

pytestmark = pytest.mark.asyncio


@pytest.mark.acceptance(
    spec="memory", scenario="aggregation runs unattended, without anyone asking for it"
)
async def test_a_pass_runs_on_start_without_anyone_asking() -> None:
    """The point of the change: the layer becomes current on its own.

    Aggregation ran only by hand for its whole first life, which made a layer
    whose premise is "what your agents already learned is here" depend on the
    user remembering to click Sync.
    """
    calls: list[str] = []

    async def _aggregate(*, actor: str) -> None:
        calls.append(actor)

    worker = AggregateWorker(aggregate=_aggregate, interval_s=3600)
    task = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(0)  # let the catch-up pass run
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Ran immediately — not after the interval, and not after a start delay.
    # A daemon that has just started is when its picture of the agents is
    # most stale.
    assert calls == [WORKER_ACTOR]


async def test_the_actor_distinguishes_a_scheduled_pass_from_a_requested_one() -> None:
    # FR-032: every pass is audited, and the log has to be able to say which
    # ones nobody asked for.
    calls: list[str] = []

    async def _aggregate(*, actor: str) -> None:
        calls.append(actor)

    await AggregateWorker(aggregate=_aggregate).run_once()

    assert calls == [WORKER_ACTOR]
    assert calls[0] != "user"


async def test_a_failing_pass_is_logged_and_the_loop_survives_it() -> None:
    attempts = 0

    async def _aggregate(*, actor: str) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("one agent's memory moved")

    worker = AggregateWorker(aggregate=_aggregate, interval_s=0)
    task = asyncio.create_task(worker.run_forever())
    for _ in range(10):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Aggregation is idempotent over a derived tree, so the next pass is
    # simply a fresh attempt; an unreadable agent must not stop the worker.
    assert attempts > 1


async def test_cancellation_is_not_swallowed_by_the_failure_guard() -> None:
    async def _aggregate(*, actor: str) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await AggregateWorker(aggregate=_aggregate, interval_s=0).run_forever()
