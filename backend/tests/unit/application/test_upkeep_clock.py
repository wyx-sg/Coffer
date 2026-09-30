"""When each unattended pass last ran and runs next (spec internal-engine
"Report when each unattended pass last ran and runs next").

"Last" is read back from the audit event each pass records; "next" from the
worker's own wait, counted against the interval as it stands now — the same
way ``wait_for_next_pass`` counts it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application.memory.aggregate_worker import AggregateWorker
from coffer.application.memory.distil_worker import DistilWorker
from coffer.application.upkeep_clock import PassClock
from coffer.domain.audit import AuditEntry
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig
from coffer.surfaces.http import internal_engine_routes

_T0 = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)


class _Audit:
    """Answers ``query(event_type=…, limit=1)`` from a fixed table."""

    def __init__(self, newest: dict[str, datetime]) -> None:
        self._newest = newest

    async def query(self, *, event_type: str | None = None, **_: Any) -> list[AuditEntry]:
        at = self._newest.get(event_type or "")
        # SQLite hands timestamps back naive; the route must make them UTC.
        return [] if at is None else [AuditEntry(id=1, timestamp=at, event_type="", actor="x")]


def test_next_is_the_wait_start_plus_the_interval_as_it_stands_now() -> None:
    clock = PassClock()
    clock.waiting("aggregate", now=_T0)
    assert clock.next_due("aggregate", 3600) == _T0 + timedelta(hours=1)
    # Shortened mid-wait: next moves earlier at once, as the wait itself does.
    assert clock.next_due("aggregate", 900) == _T0 + timedelta(minutes=15)

    clock.waiting("distil", due_in_s=60, now=_T0)
    assert clock.next_due("distil", 6 * 3600) == _T0 + timedelta(seconds=60)

    clock.running("aggregate")
    assert clock.next_due("aggregate", 3600) is None
    assert clock.next_due("curate", 3600) is None


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="each pass reports when it last ran and when it runs next",
)
async def test_each_pass_reports_when_it_last_ran_and_when_it_runs_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = PassClock()
    monkeypatch.setattr(internal_engine_routes, "PASS_CLOCK", clock)
    clock.waiting("aggregate", now=_T0)
    clock.waiting("curate", now=_T0)
    audit = _Audit({"memory_aggregated": _T0.replace(tzinfo=None) - timedelta(minutes=14)})
    cfg = GlobalInternalEngineConfig(
        model="m", updated_at=_T0, auto_curate_enabled=False, aggregate_interval_s=1800
    )

    out = (await internal_engine_routes._to_out(cfg, audit)).upkeep  # type: ignore[arg-type]

    assert out["aggregate"].last_pass_at == _T0 - timedelta(minutes=14)
    assert out["aggregate"].next_pass_at == _T0 + timedelta(minutes=30)
    # Never ran, and no worker waiting on it: neither half is invented.
    assert out["distil"].last_pass_at is None
    assert out["distil"].next_pass_at is None
    # Switched off: its timer is waiting, but no pass is coming.
    assert out["curate"].next_pass_at is None


async def test_the_workers_record_their_wait_and_clear_it_while_a_pass_runs() -> None:
    clock = PassClock()
    seen: list[datetime | None] = []

    async def _aggregate(**_: Any) -> None:
        seen.append(clock.next_due("aggregate", 3600))

    worker = AggregateWorker(aggregate=_aggregate, interval_s=3600, clock=clock)
    task = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert seen == [None]
    assert clock.next_due("aggregate", 3600) is not None

    async def _partitions() -> list[str]:
        return []

    async def _distil(uid: str, **_: Any) -> None:
        return None

    distil = DistilWorker(
        distil=_distil, list_partitions=_partitions, start_delay_s=30, clock=clock
    )
    task = asyncio.create_task(distil.run_forever())
    await asyncio.sleep(0.01)
    due = clock.next_due("distil", 6 * 3600)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert due is not None
    assert due - datetime.now(UTC) <= timedelta(seconds=30)
