"""Which collections an agent is tidying right now (spec knowledge "Record a
tidy as one change").

A tidy is opened by ``coffer knowledge tidy-start`` and closed by
``coffer knowledge tidy-finish``, both run by the agent the Tidy prompt starts.
While one is open, the edits the agent makes in that collection stay in the
working tree instead of being committed as ``disk`` writes one sweep at a time,
and closing it commits them all as one change carrying the agent's report.

The registry lives in the daemon's memory only. It is bookkeeping about a
session in progress, not knowledge: a daemon restart forgets an open tidy, and
the agent's edits are then committed as ordinary ``disk`` writes, which loses
nothing but the grouping.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class TidyRun:
    """One open tidy of one collection."""

    collection: str
    #: Wall-clock start (seconds since the epoch), for the wire.
    started_at: float
    #: Monotonic time of the last change seen in the collection's working tree.
    last_activity: float
    #: The collection's pending paths and their digests when last looked at.
    fingerprint: tuple[tuple[str, str | None], ...] = ()


class TidyRuns:
    """The open tidies, keyed by collection folder name."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, TidyRun] = {}

    def open(self, collection: str, *, started_at: float, now: float) -> TidyRun:
        """Open a tidy of ``collection``; an already open one is kept as it is."""
        with self._lock:
            run = self._runs.get(collection)
            if run is None:
                run = TidyRun(collection, started_at=started_at, last_activity=now)
                self._runs[collection] = run
            return run

    def get(self, collection: str) -> TidyRun | None:
        with self._lock:
            return self._runs.get(collection)

    def close(self, collection: str) -> TidyRun | None:
        with self._lock:
            return self._runs.pop(collection, None)

    def running(self) -> frozenset[str]:
        """The collections with an open tidy."""
        with self._lock:
            return frozenset(self._runs)

    def runs(self) -> list[TidyRun]:
        with self._lock:
            return list(self._runs.values())

    def clear(self) -> None:
        """Forget every open tidy (tests)."""
        with self._lock:
            self._runs.clear()


#: The daemon's one registry, shared by the history (which leaves a running
#: collection's edits uncommitted) and the tidy service (which opens and closes).
TIDY_RUNS = TidyRuns()

__all__ = ["TIDY_RUNS", "TidyRun", "TidyRuns"]
