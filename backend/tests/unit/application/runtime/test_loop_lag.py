"""The event-loop lag probe: samples, the window's p99 and maximum."""

from __future__ import annotations

import asyncio
import time

from coffer.application.runtime.loop_lag import LoopLagProbe, p99


def test_p99_is_the_nearest_rank() -> None:
    assert p99([0.5]) == 0.5
    values = [float(i) for i in range(1, 101)]
    assert p99(values) == 99.0
    assert p99([1.0, 2.0, 3.0]) == 3.0


def test_snapshot_before_any_sample_says_so() -> None:
    lag = LoopLagProbe(interval=0.5, window=600).snapshot()
    assert lag.p99_ms is None and lag.max_ms is None
    assert lag.samples == 0
    assert lag.window_seconds == 300.0


def test_the_window_keeps_only_the_latest_samples() -> None:
    probe = LoopLagProbe(interval=1.0, window=3)
    for seconds in (0.9, 0.001, 0.002, 0.003):
        probe.record(seconds)
    lag = probe.snapshot()
    assert lag.samples == 3
    assert lag.max_ms == 3.0  # the 900 ms sample aged out
    probe.record(-0.001)  # clock noise counts as zero
    assert probe.snapshot().samples == 3


async def test_a_blocked_loop_shows_up_as_lag() -> None:
    probe = LoopLagProbe(interval=0.01, window=50)
    task = asyncio.create_task(probe.run())
    await asyncio.sleep(0.005)
    time.sleep(0.12)  # block the loop the way a synchronous call would
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    lag = probe.snapshot()
    assert lag.samples >= 1
    assert lag.max_ms is not None and lag.max_ms >= 80
