"""The stall watch: a loop blocked past the threshold is logged with its stack."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from coffer.application.runtime.loop_lag import LoopLagProbe
from coffer.application.runtime.stall_watch import StallWatch


def _stalls(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "runtime.loop.stalled"]


def _block_the_loop_synchronously(seconds: float) -> None:
    time.sleep(seconds)


async def _run_probe_while(blocker: object, watch: StallWatch) -> None:
    probe = LoopLagProbe(interval=0.01, window=50, watch=watch)
    sampler = asyncio.create_task(probe.run())
    await asyncio.sleep(0.03)
    culprit = asyncio.create_task(blocker, name="culprit-task")  # type: ignore[arg-type]
    await culprit
    await asyncio.sleep(0.03)
    sampler.cancel()
    await asyncio.gather(sampler, return_exceptions=True)


@pytest.mark.acceptance(spec="daemon", scenario="a stalled loop is logged with what blocked it")
async def test_a_blocked_loop_is_logged_with_the_blocking_stack_and_task(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="coffer.application.runtime.stall_watch")

    async def blocker() -> None:
        _block_the_loop_synchronously(0.25)

    await _run_probe_while(blocker(), StallWatch(threshold=0.03, report_every=0.0))

    stalls = _stalls(caplog)
    assert stalls, "a 250 ms block past a 30 ms threshold must be reported"
    record = stalls[0]
    assert record.task == "culprit-task"  # type: ignore[attr-defined]
    assert "_block_the_loop_synchronously" in record.stack  # type: ignore[attr-defined]
    assert record.suppressed == 0  # type: ignore[attr-defined]


async def test_a_loop_that_keeps_up_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="coffer.application.runtime.stall_watch")

    async def idle() -> None:
        await asyncio.sleep(0.1)

    await _run_probe_while(idle(), StallWatch(threshold=0.05, report_every=0.0))
    assert _stalls(caplog) == []


async def test_repeated_stalls_are_rate_limited_and_counted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="coffer.application.runtime.stall_watch")
    watch = StallWatch(threshold=0.03, report_every=60.0)

    async def blocker() -> None:
        for _ in range(3):
            _block_the_loop_synchronously(0.15)
            await asyncio.sleep(0.02)

    await _run_probe_while(blocker(), watch)
    assert len(_stalls(caplog)) == 1
    assert watch._suppressed >= 1  # held back for the next line
