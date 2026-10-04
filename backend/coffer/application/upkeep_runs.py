"""Which upkeep passes this daemon is running right now.

An *upkeep pass* is one of the long rewrites a vault does to itself, such as
memory's ``distil`` over a partition. Each rewrites files and can be started
from three places — a button, the CLI, a timer. Two of them over the same target at the
same time is not a slower version of one; it is two writers racing over the
same directory.

So whether a pass is running is a fact about the DAEMON, not about whichever
surface happened to start it. A button that remembers "I am organising" in its
own component state forgets on the next navigation, and the second click then
starts a second pass. This registry is where that fact actually lives, keyed
by ``(kind, name)`` so every kind's targets share one table rather than
growing one each.

**It is per-process, and that is the design.** A pass runs inside the daemon
that was asked for it; there is no queue, no row and no lease. A daemon
restart is therefore the end of any pass it was running, and the registry
comes back empty — which is the truth, not a lost record. Nothing here
survives a restart and nothing here should: a claim that outlived the process
holding it would wedge a target forever, with no runner left to release it.

Release always happens in a ``finally``, so a pass that raises frees its key
on the way out.
"""

from __future__ import annotations

import contextlib
import dataclasses
import threading
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.domain.errors import UpkeepAlreadyRunning

__all__ = [
    "UPKEEP_RUNS",
    "UpkeepRun",
    "UpkeepRunRegistry",
]


@dataclass(frozen=True)
class UpkeepRun:
    """One pass in flight: what it is over, and since when."""

    kind: str
    name: str
    started_at: datetime
    #: For a run that works through several items one pass at a time (memory's
    #: Update memory): how many it has done of how many. ``None``
    #: for a pass that is one unit of work.
    done: int | None = None
    total: int | None = None


class UpkeepRunRegistry:
    """The in-process table of passes in flight.

    Guarded by a plain lock rather than an ``asyncio`` one: the claim itself
    does no I/O, and a synchronous lock lets a caller outside the event loop
    (a CLI path, a test) read the same table without needing a loop.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: dict[tuple[str, str], UpkeepRun] = {}

    # --- the claim ----------------------------------------------------------

    def claim(self, kind: str, name: str) -> bool:
        """Take the key, or report that someone else already holds it.

        Returns False rather than raising, because the two callers want
        different things from a busy target: a route refuses, a timer skips.
        """
        with self._lock:
            key = (kind, name)
            if key in self._running:
                return False
            self._running[key] = UpkeepRun(kind=kind, name=name, started_at=datetime.now(UTC))
            return True

    def release(self, kind: str, name: str) -> None:
        """Give the key back. Releasing a key nobody holds is a no-op."""
        with self._lock:
            self._running.pop((kind, name), None)

    def progress(self, kind: str, name: str, *, done: int, total: int) -> None:
        """Record how far a multi-item run has got. A key nobody holds is left
        alone: the run has ended, and progress must not resurrect it."""
        with self._lock:
            key = (kind, name)
            if key in self._running:
                self._running[key] = dataclasses.replace(self._running[key], done=done, total=total)

    # --- reading it ---------------------------------------------------------

    def running(self, kind: str, name: str) -> UpkeepRun | None:
        with self._lock:
            return self._running.get((kind, name))

    def list_running(self) -> list[UpkeepRun]:
        """Everything in flight, oldest first."""
        with self._lock:
            return sorted(self._running.values(), key=lambda run: (run.started_at, run.kind))

    # --- the two ways to hold one -------------------------------------------

    @contextlib.contextmanager
    def guard(self, kind: str, name: str) -> Iterator[None]:
        """Hold the key for the block, or refuse the whole thing.

        What a surface wants: a second request over a target already being
        rewritten is refused outright (``UpkeepAlreadyRunning`` → 409) rather
        than queued, because the caller asked to start a pass and no pass is
        going to start.
        """
        if not self.claim(kind, name):
            raise UpkeepAlreadyRunning(kind, name)
        try:
            yield
        finally:
            self.release(kind, name)

    @contextlib.asynccontextmanager
    async def claimed(self, kind: str, name: str) -> AsyncIterator[bool]:
        """Hold the key for the block if it was free; say whether it was.

        What a timer wants: a sweep that finds a target already being
        rewritten by hand skips it and moves on. It must not queue behind it
        (the next tick sweeps everything again anyway) and must not fail the
        sweep (a target being busy is an ordinary state, not a fault).
        """
        claimed = self.claim(kind, name)
        try:
            yield claimed
        finally:
            if claimed:
                self.release(kind, name)


#: The one registry the daemon shares. A route and a worker must consult the
#: SAME table or the whole exercise is pointless, so this is a module-level
#: singleton rather than something each composition root builds its own copy
#: of. Tests that want isolation construct their own ``UpkeepRunRegistry``.
UPKEEP_RUNS = UpkeepRunRegistry()
