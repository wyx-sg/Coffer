"""Audit log application service — thin wrapper over AuditRepo."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from coffer.application.repos import AuditRepo
from coffer.domain.audit import AuditEntry
from coffer.domain.resource import Resource

_logger = logging.getLogger(__name__)


class AuditService:
    """Record + query audit entries.

    ``record`` generates the timestamp and decomposes the ``Resource`` the
    event is about, so callers don't repeat that. Each row keeps two different
    things on purpose: ``resource_id`` ties the event to the resource, and
    ``resource_kind``/``resource_name`` record the LABEL it carried at that
    moment. That is what lets a rename leave the trail alone — the history says
    what the thing was called when each event happened, and still reads as one
    history.

    The service used to be handed a resolver so it could look that id up from a
    ``(kind, name)`` pair. It is handed the resource itself now, which is
    neither a lookup nor a failure mode: the caller performing the mutation
    already has the row.
    """

    def __init__(self, repo: AuditRepo) -> None:
        self._repo = repo

    async def record(
        self,
        event_type: str,
        *,
        resource: Resource | None = None,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> None:
        await self._repo.insert(
            AuditEntry(
                id=None,
                timestamp=datetime.now(tz=UTC),
                event_type=event_type,
                resource_id=resource.id if resource else None,
                resource_kind=resource.kind if resource else None,
                resource_name=resource.name if resource else None,
                actor=actor,
                details=details or {},
            )
        )
        # Mirror every audited event into the log. Coffer used to log only its
        # failures — a live daemon.log held 4,277 lines of which 62 were
        # Coffer's own, all one error type, and a search for
        # `credential_read`, `agent_mcp_installed`, `provider_switched`,
        # `resource_deleted`, `skill_bound`, `token_rotated` and
        # `agent_config_file_written` across two months of logs returned
        # nothing at all. The audit table already decides what is worth
        # recording; this makes that same decision legible to whoever is
        # tailing a log rather than querying SQLite.
        #
        # `details` is NOT logged. The audit table applies each kind's redactor
        # before storing it, and re-deriving that here would duplicate the one
        # place that knows which fields carry secrets.
        _logger.info(
            "coffer.%s",
            event_type,
            extra={
                "event": event_type,
                "resource": resource.name if resource else None,
                "resource_kind": resource.kind if resource else None,
                "resource_uid": resource.uid if resource else None,
                "actor": actor,
            },
        )

    async def query(
        self,
        *,
        resource: Resource | None = None,
        kind: str | None = None,
        event_type: str | None = None,
        event_prefix: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """One resource's history, or a slice of everything.

        Passing ``resource`` asks for that resource's trail and gets it whole,
        including the rows written under a name it no longer has: the filter is
        its id, not its current label. ``kind`` alone is the coarser filter the
        activity page uses.
        """
        return await self._repo.query(
            kind=kind,
            resource_id=resource.id if resource else None,
            event_type=event_type,
            event_prefix=event_prefix,
            since=since,
            limit=limit,
        )
