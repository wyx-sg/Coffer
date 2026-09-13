"""Audit log application service — thin wrapper over AuditRepo."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from coffer.application.repos import AuditRepo
from coffer.domain.audit import AuditEntry
from coffer.domain.resource import ResourceRef

_logger = logging.getLogger(__name__)


class AuditService:
    """Record + query audit entries.

    ``record`` generates the timestamp and decomposes a ``ResourceRef`` so
    callers don't repeat that. It also resolves the resource's stable row id,
    which is what lets a rename leave the trail alone: the rows keep the name
    the resource had when the event happened, and the id is what ties them
    together. ``resolve_resource_id`` is injected rather than imported so this
    service keeps its single dependency on ``AuditRepo`` — the resource side
    already depends on this one.
    """

    def __init__(
        self,
        repo: AuditRepo,
        resolve_resource_id: Callable[[str, str], Awaitable[int | None]] | None = None,
    ) -> None:
        self._repo = repo
        self._resolve_resource_id = resolve_resource_id

    async def _id_for(self, ref: ResourceRef | None) -> int | None:
        if ref is None or self._resolve_resource_id is None:
            return None
        try:
            return await self._resolve_resource_id(ref.kind, ref.name)
        except Exception:
            # An unresolvable id costs the row its stable pointer, not the
            # event: the label still records what happened and to what.
            _logger.debug("audit.resource_id_unresolved", exc_info=True)
            return None

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
                resource_id=await self._id_for(ref),
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
        # Asking for one resource's history resolves its id first, so the trail
        # comes back whole even if the resource has been renamed since — the
        # rows themselves still carry whatever it was called at the time.
        resource_id = None
        if kind is not None and name is not None:
            resource_id = await self._id_for(ResourceRef(kind, name))
        return await self._repo.query(
            kind=kind,
            name=name,
            resource_id=resource_id,
            event_type=event_type,
            since=since,
            limit=limit,
        )
