"""When Coffer last read the agents' memory, and whose it could not read (spec
memory "Report the last read of the agents' memory").

The Memory page's header says "Read 14 min ago", and "· 1 agent failed" when
the last read left one agent's memory unread, with a banner naming the agent,
the path and — so the reader knows what they are looking at — when that
agent's memory was last read in full. Every aggregation, scheduled or asked
for, already records a ``memory_aggregated`` audit event with what failed, so
the answer is read back from the log rather than kept in the daemon: it
survives a restart, and it is the same answer whoever started the read.

Only the newest event decides whether something failed; earlier ones are
consulted only for the failing agent's last clean read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEntry, AuditEventType

#: How far back to look for a failing agent's last clean read. Hourly reads
#: make this two days; older than that the banner simply omits the date.
_HISTORY = 50


@dataclass(frozen=True)
class ReadFailure:
    """One agent's memory the last read could not parse."""

    agent: str
    path: str
    reason: str
    #: When that agent's memory was last read with nothing failing, if known.
    last_read_at: datetime | None


@dataclass(frozen=True)
class Reading:
    """The last read of the agents' memory, or none yet."""

    read_at: datetime | None
    failures: tuple[ReadFailure, ...]


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _failures_of(entry: AuditEntry) -> list[dict[str, Any]]:
    """The failures one ``memory_aggregated`` event recorded, with their agents."""
    details = (entry.details or {}).get("failure_details") or []
    return [f for f in details if isinstance(f, dict)]


def _last_clean_read(agent: str, older: Sequence[AuditEntry]) -> datetime | None:
    for entry in older:
        if all(f.get("agent") != agent for f in _failures_of(entry)):
            return _utc(entry.timestamp)
    return None


def reading_of(entries: Sequence[AuditEntry]) -> Reading:
    """The reading the newest-first ``memory_aggregated`` events describe."""
    if not entries:
        return Reading(read_at=None, failures=())
    newest, older = entries[0], entries[1:]
    return Reading(
        read_at=_utc(newest.timestamp),
        failures=tuple(
            ReadFailure(
                agent=str(f.get("agent", "")),
                path=str(f.get("path", "")),
                reason=str(f.get("reason", "")),
                last_read_at=_last_clean_read(str(f.get("agent", "")), older)
                if f.get("agent")
                else None,
            )
            for f in _failures_of(newest)
        ),
    )


async def last_reading(audit: AuditService) -> Reading:
    """Read the answer back from the audit log."""
    entries = await audit.query(event_type=AuditEventType.MEMORY_AGGREGATED.value, limit=_HISTORY)
    return reading_of(entries)


__all__ = ["ReadFailure", "Reading", "last_reading", "reading_of"]
