"""When each unattended pass last ran and when it runs next (spec internal-engine
"Report when each unattended pass last ran and runs next").

A switch and an interval say what the operator asked for; they do not say
whether it is happening. The Memory page's header
answers that with one line — "Last pass 2 h ago · next in 58 min" — and the two
halves of that line come from two different places, on purpose.

**Last** is read from the audit log. Every pass already records an event when
it changes something (``memory_synced``), whoever asked for it — the timer,
Sync now or the CLI. So the
newest one is the honest answer to "when did this last happen", and it survives
a daemon restart, which an in-process record would not.

**Next** is the worker's own, because nothing but the worker knows when its
wait began. The worker tells :data:`PASS_CLOCK` when it starts waiting (and,
for a worker with a start delay, how long that first wait is), and when a pass
begins. The due time is then worked out against the interval as it stands
*now*, which is exactly how ``wait_for_next_pass`` counts: shortening the
interval moves "next" earlier at once, the way the wait itself does. While a
pass is running there is no "next" to report, and a worker that is not running
on this daemon reports none either.

Per-process like ``upkeep_runs``, and for the same reason: a daemon restart
ends every wait, and the next boot's workers record their own.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.internal_engine_config import MEMORY_SYNC

#: The audit event each pass records when it finishes — the source of "last".
PASS_EVENTS: dict[str, str] = {
    MEMORY_SYNC: AuditEventType.MEMORY_SYNCED.value,
}


@dataclass(frozen=True)
class _Wait:
    since: datetime
    #: A fixed first wait (a worker's start delay); ``None`` means the interval.
    due_in_s: float | None = None


class PassClock:
    """The in-process record of each worker's current wait."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._waits: dict[str, _Wait] = {}

    def waiting(
        self, pass_name: str, *, due_in_s: float | None = None, now: datetime | None = None
    ) -> None:
        """The worker has started waiting for its next pass."""
        with self._lock:
            self._waits[pass_name] = _Wait(since=now or datetime.now(UTC), due_in_s=due_in_s)

    def running(self, pass_name: str) -> None:
        """A pass has begun; there is no "next" until it ends."""
        with self._lock:
            self._waits.pop(pass_name, None)

    def next_due(self, pass_name: str, interval_s: float) -> datetime | None:
        """When the worker's current wait ends, against ``interval_s`` as it
        stands now; ``None`` while a pass runs or no worker is waiting."""
        with self._lock:
            wait = self._waits.get(pass_name)
        if wait is None:
            return None
        seconds = wait.due_in_s if wait.due_in_s is not None else interval_s
        return wait.since + timedelta(seconds=seconds)


#: The one clock the daemon's workers and the settings route share.
PASS_CLOCK = PassClock()


async def last_pass_at(audit: AuditService, pass_name: str) -> datetime | None:
    """When ``pass_name`` last finished on this machine, by anyone's request."""
    rows = await audit.query(event_type=PASS_EVENTS[pass_name], limit=1)
    return rows[0].timestamp if rows else None


__all__ = ["PASS_CLOCK", "PASS_EVENTS", "PassClock", "last_pass_at"]
