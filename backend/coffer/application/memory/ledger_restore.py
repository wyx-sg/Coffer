"""Rebuild the session ledger from the audit log (spec memory "Remember what a
session was given across daemon restarts").

Every fire that delivered something is one ``memory_delivery_fired`` event
naming its moment, its session and its notes (spec memory "Audit every
delivery fire"). Reading the recent ones back, oldest first, gives the ledger
exactly what earlier daemons gave, so a restart does not bring a note in again
in a session that is still going.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from coffer.application.memory.hook_service import MOMENT_PROMPT
from coffer.application.memory.session_ledger import MAX_SESSIONS, SessionLedger
from coffer.domain.audit import AuditEntry, AuditEventType

#: How far back a restart looks. A session idle for longer than this is
#: treated as a new one if it resumes.
RESTORE_WINDOW = timedelta(days=7)
#: The most fire events one restore reads.
MAX_RESTORED_EVENTS = MAX_SESSIONS * 8


class AuditReader(Protocol):
    async def query(
        self,
        *,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> Sequence[AuditEntry]: ...


def _names(value: object) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


async def restore_from_audit(
    ledger: SessionLedger, audit: AuditReader, *, now: datetime | None = None
) -> int:
    """Replay the recent delivery fires into ``ledger``; return how many applied."""
    since = (now or datetime.now(tz=UTC)) - RESTORE_WINDOW
    entries = await audit.query(
        event_type=AuditEventType.MEMORY_DELIVERY_FIRED.value,
        since=since,
        limit=MAX_RESTORED_EVENTS,
    )
    applied = 0
    # Newest first from the log; oldest first here, so the ledger's own
    # most-recent order — which decides what it forgets first — is kept.
    for entry in reversed(list(entries)):
        details = entry.details or {}
        session_id = details.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        moment = details.get("moment")
        if moment == MOMENT_PROMPT:
            notes = _names(details.get("notes"))
            if notes:
                ledger.mark_delivered(session_id, notes)
                applied += 1
    return applied


__all__ = ["MAX_RESTORED_EVENTS", "RESTORE_WINDOW", "restore_from_audit"]
