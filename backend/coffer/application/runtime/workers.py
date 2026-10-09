"""What each background worker is doing, for the daemon's status.

The supervisor (:mod:`supervisor`) knows which tasks are alive and counts their
crashes; it cannot say what a live one is doing. A worker built on
:class:`~coffer.application.runtime.wakeable.WakeableLoop` reports here instead:
how it is woken, whether it is waiting, running or parked, how long its last run
took and how it ended, and when its fallback timer will run it next if nothing
wakes it first. ``GET /api/v1/daemon/status`` and ``coffer daemon status
--workers`` read :func:`workers`.

The route needs no token, so a worker's name is a fixed string, never a
channel, server or chat.
"""

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal

WorkerState = Literal["waiting", "running", "parked"]


class WorkerMode(enum.StrEnum):
    """How a worker is woken."""

    #: Only by an event (a queued item, a file change, a hint).
    EVENT = "event"
    #: By an event, or by a fallback timer that catches an event that was lost.
    EVENT_FALLBACK = "event+fallback"
    #: Parked with no timer while nothing needs it.
    ON_DEMAND = "on-demand"


@dataclass(frozen=True)
class WorkerRecord:
    """One worker, as the status reports it."""

    name: str
    mode: WorkerMode
    state: WorkerState = "waiting"
    runs: int = 0
    failures: int = 0
    last_started_at: datetime | None = None
    last_duration_ms: float | None = None
    #: Whether the last run ended without raising; ``None`` before the first.
    last_ok: bool | None = None
    #: When it runs next if nothing else wakes it: the fallback's deadline, or
    #: the end of the settle once it is poked. ``None`` while it waits only for
    #: an event, runs, or is parked.
    next_run_at: datetime | None = None


class WorkerRegistry:
    """The workers running now, by name. Safe to read from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, WorkerRecord] = {}
        #: Which registration owns each name, so a stopped worker cannot drop
        #: a newer one that took the same name.
        self._owners: dict[str, object] = {}

    def register(self, name: str, mode: WorkerMode) -> object:
        """Start reporting ``name``; returns the token the updates take."""
        token = object()
        with self._lock:
            self._records[name] = WorkerRecord(name=name, mode=mode)
            self._owners[name] = token
        return token

    def drop(self, name: str, token: object) -> None:
        with self._lock:
            if self._owners.get(name) is token:
                del self._owners[name]
                del self._records[name]

    def waiting(self, name: str, token: object, fallback: float | None) -> None:
        due = None if fallback is None else datetime.now(tz=UTC) + timedelta(seconds=fallback)
        self._update(name, token, state="waiting", next_run_at=due)

    def parked(self, name: str, token: object) -> None:
        self._update(name, token, state="parked", next_run_at=None)

    def started(self, name: str, token: object) -> None:
        self._update(
            name, token, state="running", next_run_at=None, last_started_at=datetime.now(tz=UTC)
        )

    def finished(self, name: str, token: object, *, ok: bool, seconds: float) -> None:
        with self._lock:
            record = self._records.get(name)
            if record is None or self._owners.get(name) is not token:
                return
            # The state stays ``running`` until the loop says what it waits for.
            self._records[name] = replace(
                record,
                runs=record.runs + 1,
                failures=record.failures + (0 if ok else 1),
                last_duration_ms=round(seconds * 1000, 1),
                last_ok=ok,
            )

    def snapshot(self) -> list[WorkerRecord]:
        """Every worker, by name."""
        with self._lock:
            return [self._records[n] for n in sorted(self._records)]

    def _update(self, name: str, token: object, **changes: object) -> None:
        with self._lock:
            record = self._records.get(name)
            if record is not None and self._owners.get(name) is token:
                self._records[name] = replace(record, **changes)  # type: ignore[arg-type]


_WORKERS = WorkerRegistry()


def workers() -> WorkerRegistry:
    """The process-wide registry."""
    return _WORKERS


__all__ = ["WorkerMode", "WorkerRecord", "WorkerRegistry", "WorkerState", "workers"]
