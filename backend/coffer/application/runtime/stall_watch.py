"""Name what is blocking the event loop, while it still is.

The lag probe (:mod:`loop_lag`) measures a stall only after the loop wakes up
again, by which time whatever blocked it has returned and left no trace: the
status shows a 120 ms maximum and nothing says what took it. Finding the call
meant guessing from the code.

This watch is a small daemon thread beside the loop. Each time the probe goes
to sleep it *arms* the watch with the moment it expects to be back, plus a
threshold. If that moment passes without the probe re-arming, the loop is
stuck right now, so the thread takes the loop thread's current stack
(``sys._current_frames``) and the task the loop is running, and logs one
``runtime.loop.stalled`` line with both. The culprit is caught in the act.

It costs a thread that wakes when the probe does (twice a second) and does
nothing else. Lines are rate-limited, so a loop that stalls over and over
logs one line per :data:`REPORT_EVERY_SECONDS` with the count it held back.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback
from dataclasses import dataclass

_logger = logging.getLogger(__name__)

#: A wake-up this much later than due is a stall worth a stack.
DEFAULT_THRESHOLD_SECONDS = 0.1
#: At most one stall line this often; the rest are counted into the next one.
REPORT_EVERY_SECONDS = 10.0
#: Innermost frames kept: the blocking call and enough callers to place it.
_STACK_FRAMES = 25


@dataclass(frozen=True)
class Stall:
    """One stall caught in progress."""

    task: str | None
    stack: str
    suppressed: int


class StallWatch:
    """Arm before each sleep (from the loop); the thread reports a missed deadline."""

    def __init__(
        self,
        *,
        threshold: float = DEFAULT_THRESHOLD_SECONDS,
        report_every: float = REPORT_EVERY_SECONDS,
    ) -> None:
        self._threshold = threshold
        self._report_every = report_every
        self._cond = threading.Condition()
        self._deadline: float | None = None
        self._stopped = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None
        self._thread: threading.Thread | None = None
        self._last_report = float("-inf")
        self._suppressed = 0

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start watching ``loop``; call from the loop's own thread."""
        self._loop = loop
        self._loop_thread = threading.get_ident()
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopped = False
        self._thread = threading.Thread(target=self._run, name="loop-stall-watch", daemon=True)
        self._thread.start()

    def arm(self, due_in: float) -> None:
        """The loop expects to run again within ``due_in`` seconds."""
        with self._cond:
            self._deadline = time.monotonic() + due_in + self._threshold
            self._cond.notify()

    def stop(self) -> None:
        with self._cond:
            self._stopped = True
            self._cond.notify()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        with self._cond:
            while not self._stopped:
                deadline = self._deadline
                if deadline is None:
                    self._cond.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    self._cond.wait(remaining)
                    continue
                # Missed: the loop has not re-armed. Report once per deadline.
                self._deadline = None
                stall = self._capture()
                if stall is not None:
                    _logger.warning(
                        "runtime.loop.stalled",
                        extra={
                            "task": stall.task,
                            "blocked_ms_at_least": round(self._threshold * 1000),
                            "stack": stall.stack,
                            "suppressed": stall.suppressed,
                        },
                    )

    def _capture(self) -> Stall | None:
        """The stall to log, or ``None`` when rate-limited (counted instead)."""
        now = time.monotonic()
        if now - self._last_report < self._report_every:
            self._suppressed += 1
            return None
        frame = sys._current_frames().get(self._loop_thread or -1)
        if frame is None:
            return None
        stack = "".join(traceback.format_stack(frame, limit=_STACK_FRAMES))
        current = asyncio.current_task(self._loop) if self._loop is not None else None
        suppressed, self._suppressed = self._suppressed, 0
        self._last_report = now
        return Stall(
            task=current.get_name() if current is not None else None,
            stack=stack,
            suppressed=suppressed,
        )
