"""Audit log application service — thin wrapper over AuditRepo."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.application.repos import AuditRepo
from coffer.domain.audit import AuditEntry
from coffer.domain.resource import ResourceRef


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
