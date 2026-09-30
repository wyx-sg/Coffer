"""One Homebrew install of a required command, while it runs and after.

The job keeps the last :data:`OUTPUT_LINES` lines of the command's merged
output, numbered from the first line it printed, so a caller that polls can
ask for only what it has not seen (``since``). Lines are appended from the
worker thread the installer runs in and read from the event loop, hence the
lock.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

#: How much output a job keeps.
OUTPUT_LINES = 2000
#: How much of it the finishing audit record carries.
AUDIT_TAIL_LINES = 40


class InstallState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class InstallSnapshot:
    command: str
    formula: str
    #: ``install`` for a missing command, ``upgrade`` for an outdated one.
    action: str
    argv: tuple[str, ...]
    state: InstallState
    exit_code: int | None
    started_at: datetime
    finished_at: datetime | None
    #: The number of the first line in ``lines``; lines before it were dropped
    #: or were not asked for.
    first_line: int
    lines: tuple[str, ...]
    #: The number the next line printed will get — the ``since`` to poll with.
    next_line: int


class InstallJob:
    def __init__(
        self,
        *,
        command: str,
        formula: str,
        action: str,
        argv: tuple[str, ...],
        started_at: datetime,
    ) -> None:
        self.command = command
        self.formula = formula
        self.action = action
        self.argv = argv
        self.started_at = started_at
        self.finished_at: datetime | None = None
        self.exit_code: int | None = None
        self.state = InstallState.RUNNING
        self._lines: deque[str] = deque(maxlen=OUTPUT_LINES)
        self._total = 0
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self.state is InstallState.RUNNING

    def append(self, line: str) -> None:
        with self._lock:
            self._lines.append(line)
            self._total += 1

    def tail(self, count: int = AUDIT_TAIL_LINES) -> list[str]:
        with self._lock:
            return list(self._lines)[-count:]

    def finish(self, exit_code: int | None, at: datetime) -> None:
        self.exit_code = exit_code
        self.finished_at = at
        self.state = InstallState.SUCCEEDED if exit_code == 0 else InstallState.FAILED

    def snapshot(self, since: int = 0) -> InstallSnapshot:
        with self._lock:
            kept_from = self._total - len(self._lines)
            first = max(since, kept_from)
            lines = tuple(list(self._lines)[first - kept_from :]) if first < self._total else ()
            total = self._total
        return InstallSnapshot(
            command=self.command,
            formula=self.formula,
            action=self.action,
            argv=self.argv,
            state=self.state,
            exit_code=self.exit_code,
            started_at=self.started_at,
            finished_at=self.finished_at,
            first_line=min(first, total),
            lines=lines,
            next_line=total,
        )


__all__ = [
    "AUDIT_TAIL_LINES",
    "OUTPUT_LINES",
    "InstallJob",
    "InstallSnapshot",
    "InstallState",
]
