"""Update memory's progress, and what the page reads off the last read (spec
memory "Show Update memory's progress", "Report the last read of the agents'
memory").

The progress is the in-flight entry Update memory holds while it runs — the
one the header turns into "Distilling 2 of 5 partitions". The last read is
worked out from the newest ``memory_aggregated`` audit events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application.memory.aggregate import AggregationResult
from coffer.application.memory.reading import reading_of
from coffer.application.memory.service import KIND_MEMORY
from coffer.application.memory.update import UPDATE_RUN, update_memory
from coffer.application.upkeep_runs import UpkeepRunRegistry
from coffer.domain.audit import AuditEntry
from coffer.domain.memory.note import TYPE_PROJECT
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.memory.raw_store import StoredRawEntry, write_raw_entry

_T0 = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)


def _raw(partition: str) -> None:
    write_raw_entry(
        StoredRawEntry(
            partition=partition,
            agent="codex",
            native_path=f"/native/{partition}.md",
            captured_at="2026-01-01T00:00:00+00:00",
            entry=RawEntry(
                title=f"{partition} lesson",
                description="d",
                type=TYPE_PROJECT,
                body="b",
                anchor=partition,
                project_root=f"/home/dev/{partition}",
            ),
        )
    )


@dataclass
class _Row:
    uid: str
    name: str


class _Service:
    def __init__(self, runs: UpkeepRunRegistry, names: list[str]) -> None:
        self._runs = runs
        self._rows = [_Row(uid=f"UID-{n}", name=n) for n in names]
        self.seen: list[tuple[int | None, int | None]] = []
        self.read_while: list[bool] = []

    async def aggregate(self, *, actor: str) -> AggregationResult:
        run = self._runs.running(KIND_MEMORY, UPDATE_RUN)
        self.read_while.append(run is not None and run.total is None)
        return AggregationResult((), 0, 0, 0, ())

    async def list_partitions(self) -> list[_Row]:
        return self._rows

    async def distil(self, uid: str, *, actor: str) -> None:
        run = self._runs.running(KIND_MEMORY, UPDATE_RUN)
        assert run is not None
        self.seen.append((run.done, run.total))


@pytest.mark.acceptance(
    spec="memory", scenario="update memory reports how many partitions it has distilled"
)
async def test_update_memory_reports_how_many_partitions_it_has_distilled() -> None:
    for name in ("alpha", "beta", "gamma"):
        _raw(name)
    runs = UpkeepRunRegistry()
    service = _Service(runs, ["alpha", "beta", "gamma", "idle"])

    result = await update_memory(service, actor="user", runs=runs)  # type: ignore[arg-type]

    # Reading first, with no count yet; then one step per partition that had
    # something to distil — "idle" held nothing and is not counted.
    assert service.read_while == [True]
    assert service.seen == [(0, 3), (1, 3), (2, 3)]
    assert result.distilled == ("alpha", "beta", "gamma")
    assert runs.running(KIND_MEMORY, UPDATE_RUN) is None


def _event(at: datetime, **details: Any) -> AuditEntry:
    return AuditEntry(
        id=None, timestamp=at, event_type="memory_aggregated", actor="x", details=details
    )


@pytest.mark.acceptance(
    spec="memory", scenario="the last read and an agent it could not read are reported"
)
def test_the_last_read_and_an_agent_it_could_not_read_are_reported() -> None:
    failed = {"agent": "codex", "path": "/h/.codex/memories", "reason": "not readable"}
    entries = [
        _event(_T0, failures=["/h/.codex/memories"], failure_details=[failed]),
        _event(_T0 - timedelta(hours=1), failures=["/h/.codex/memories"], failure_details=[failed]),
        _event(_T0 - timedelta(days=3), failures=[], failure_details=[]),
    ]

    reading = reading_of(entries)

    assert reading.read_at == _T0
    [failure] = reading.failures
    assert (failure.agent, failure.path, failure.reason) == (
        "codex",
        "/h/.codex/memories",
        "not readable",
    )
    # Its memories stand as the last read that left nothing of it unread.
    assert failure.last_read_at == _T0 - timedelta(days=3)


def test_no_read_yet_and_a_clean_read() -> None:
    assert reading_of([]).read_at is None
    clean = reading_of([_event(_T0.replace(tzinfo=None), failures=[], failure_details=[])])
    assert clean.read_at == _T0
    assert clean.failures == ()


def test_an_old_event_that_names_no_agent_is_not_a_clean_read() -> None:
    entries = [
        _event(
            _T0, failures=["/p"], failure_details=[{"agent": "cc", "path": "/p", "reason": "r"}]
        ),
        _event(_T0 - timedelta(hours=1), failures=["/p"]),
    ]
    [failure] = reading_of(entries).failures
    assert failure.last_read_at is None
    # An event from before agents were recorded still reports its paths.
    [legacy] = reading_of(entries[1:]).failures
    assert (legacy.agent, legacy.path, legacy.last_read_at) == ("", "/p", None)
