"""A clock that keeps counting while the computer sleeps
(ADR timeouts-and-intervals-count-time-the-computer-slept).

``time.monotonic`` — and with it ``asyncio``'s timers and ``subprocess``'s
``timeout`` — stops while the machine sleeps on macOS (``mach_absolute_time``)
and on Linux (``CLOCK_MONOTONIC``). A 120-second deadline then needs 120 awake
seconds, which a closed laptop collects two seconds per PowerNap wake: one
measured fetch took four and a half hours to time out. Deadlines and intervals
a person reads as wall time count on this clock instead.

The clock is chosen by what the ``time`` module offers, not by asking which OS
this is: ``CLOCK_BOOTTIME`` (Linux) counts suspend; where it is missing,
``CLOCK_MONOTONIC`` through ``clock_gettime`` is the one that counts sleep
(macOS); with neither, ``time.time``.
"""

from __future__ import annotations

import time

_CLOCK_ID: int | None = getattr(time, "CLOCK_BOOTTIME", None)
if _CLOCK_ID is None and hasattr(time, "clock_gettime"):
    _CLOCK_ID = time.CLOCK_MONOTONIC


def now() -> float:
    """Seconds on a clock that counts time asleep, from an arbitrary origin."""
    return time.clock_gettime(_CLOCK_ID) if _CLOCK_ID is not None else time.time()


def slept_since(started: float, started_awake: float) -> float:
    """How many seconds the machine slept since ``started`` (``now()``) and
    ``started_awake`` (``time.monotonic()``) were read together; ``0`` where
    the two clocks agree."""
    return max(0.0, (now() - started) - (time.monotonic() - started_awake))


__all__ = ["now", "slept_since"]
