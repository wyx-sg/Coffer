"""Audit log application service — thin wrapper over AuditRepo."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from coffer.application.repos import AuditRepo
from coffer.domain.audit import AuditEntry
from coffer.domain.resource import ResourceRef

_logger = logging.getLogger(__name__)


class AuditService:
    """Record + query audit entries.

    `record` generates the timestamp + handles the (kind, name)
    decomposition from a ResourceRef so callers don't repeat that.
    """

    def __init__(self, repo: AuditRepo) -> None:
        self._repo = repo

    async def record(
        self,
        event_type: str,
        *,
        ref: ResourceRef | None = None,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> None:
        await self._repo.insert(
            AuditEntry(
                id=None,
                timestamp=datetime.now(tz=UTC),
                event_type=event_type,
                resource_kind=ref.kind if ref else None,
                resource_name=ref.name if ref else None,
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
                "resource": str(ref) if ref else None,
                "actor": actor,
            },
        )

    async def query(
        self,
        *,
        kind: str | None = None,
        name: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        return await self._repo.query(
            kind=kind,
            name=name,
            event_type=event_type,
            since=since,
            limit=limit,
        )
