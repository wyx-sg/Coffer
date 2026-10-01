"""Event-loop lag: how late the daemon's loop wakes up, as a p99 over a window.

Everything the daemon does runs on one ``asyncio`` loop, so one synchronous
call that blocks it — a file walk, a subprocess wait, a slow SQLite commit on
the loop thread — stalls every request, every channel and every turn at once,
and shows up nowhere: each of them just looks slow. The probe makes the stall
itself visible.

It sleeps for ``interval`` seconds and measures how much later than asked the
loop woke it: the lag is the time the loop spent on something else. Samples
are kept for a rolling window, and ``GET /api/v1/daemon/status`` (and
``coffer daemon status``) report the window's p99 and maximum. A healthy idle
daemon reads a millisecond or two; hundreds of milliseconds means something is
blocking the loop.
"""

from __future__ import annotations

import asyncio
import math
from collections import deque
from dataclasses import dataclass

#: Seconds between samples.
DEFAULT_INTERVAL_SECONDS = 0.5
#: Samples kept: 600 at 0.5 s is a five-minute window.
DEFAULT_WINDOW_SAMPLES = 600


@dataclass(frozen=True)
class LoopLag:
    """The window's reading, in milliseconds; ``None`` before the first sample."""

    p99_ms: float | None
    max_ms: float | None
    samples: int
    window_seconds: float


def p99(values: list[float]) -> float:
    """The 99th percentile by nearest rank (``values`` non-empty)."""
    ordered = sorted(values)
    rank = max(1, math.ceil(0.99 * len(ordered)))
    return ordered[rank - 1]


class LoopLagProbe:
    """Samples the loop's wake-up delay; :meth:`run` is the sampling loop."""

    def __init__(
        self,
        *,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        window: int = DEFAULT_WINDOW_SAMPLES,
    ) -> None:
        self._interval = interval
        self._window = window
        self._samples: deque[float] = deque(maxlen=window)

    def record(self, lag_seconds: float) -> None:
        """Add one sample (negative clock noise counts as zero)."""
        self._samples.append(max(lag_seconds, 0.0))

    async def run(self) -> None:
        """Sample forever; cancel to stop."""
        loop = asyncio.get_running_loop()
        while True:
            started = loop.time()
            await asyncio.sleep(self._interval)
            self.record(loop.time() - started - self._interval)

    def snapshot(self) -> LoopLag:
        samples = list(self._samples)
        window_seconds = self._interval * self._window
        if not samples:
            return LoopLag(p99_ms=None, max_ms=None, samples=0, window_seconds=window_seconds)
        return LoopLag(
            p99_ms=round(p99(samples) * 1000, 2),
            max_ms=round(max(samples) * 1000, 2),
            samples=len(samples),
            window_seconds=window_seconds,
        )


_PROBE = LoopLagProbe()


def probe() -> LoopLagProbe:
    """The daemon's one probe (started by the composition root)."""
    return _PROBE
