"""A plain timer loop reports to the worker registry (spec daemon "Report each
background worker's schedule on the status")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.runtime.workers import TimedWorker, WorkerMode, WorkerRegistry


@pytest.mark.acceptance(spec="daemon", scenario="a plain timer loop reports as a timer worker")
def test_a_timer_loop_reports_its_passes_and_its_sleep() -> None:
    registry = WorkerRegistry()
    report = TimedWorker("retention-worker", registry)
    with report.pass_():
        (running,) = registry.snapshot()
        assert running.state == "running" and running.mode is WorkerMode.TIMER
    report.sleeping(3600)

    (record,) = registry.snapshot()
    assert (record.name, record.state, record.runs, record.failures) == (
        "retention-worker",
        "waiting",
        1,
        0,
    )
    assert record.last_ok is True
    assert record.next_run_at is not None
    assert abs(record.next_run_at - (datetime.now(tz=UTC) + timedelta(hours=1))) < timedelta(
        seconds=5
    )

    report.close()
    assert registry.snapshot() == []


def test_a_pass_that_raises_is_counted_and_the_error_goes_on() -> None:
    registry = WorkerRegistry()
    report = TimedWorker("sync-worker", registry)
    with pytest.raises(RuntimeError), report.pass_():
        raise RuntimeError("boom")
    (record,) = registry.snapshot()
    assert (record.runs, record.failures, record.last_ok, record.state) == (1, 1, False, "waiting")
    assert record.next_run_at is None
