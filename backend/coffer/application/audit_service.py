"""Audit log application service — thin wrapper over AuditRepo."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from coffer.application.repos import AuditRepo
from coffer.application.runtime import correlation
from coffer.domain.audit import AuditEntry
from coffer.domain.pagination import Page, decode_cursor, paginate, position_of, time_and_id
from coffer.domain.resource import Resource

_logger = logging.getLogger(__name__)


class AuditService:
    """Record + query audit entries.

    ``record`` generates the timestamp and decomposes the ``Resource`` the
    event is about, so callers don't repeat that. Each row keeps two different
    things on purpose: ``resource_uid`` ties the event to the resource, and
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
        """File one audit row.

        ``resource`` is the resource itself, and passing the whole object is
        what lets this file its **uid** alongside the label — which is what makes
        the history survive a rename, and what makes "this resource's history"
        a question about one object rather than about a name two objects may
        have worn in turn. It is optional because some events name no resource
        at all: the row then records the event and its actor and joins to
        nothing, which is the truth about it. There is deliberately no way to
        audit a resource by label alone — the moment there is one, something
        will use it, and that resource's history splits at the next rename.

        The row also takes the correlation ids bound where it is written — the
        request's or the turn's trace id, and a turn's conversation and turn —
        so it joins the MCP invocations and daemon log lines of the same unit of
        work (spec resource-framework "Correlate the audit log, the MCP
        invocation log and the daemon log by one trace id").
        """
        bound = correlation.current()
        await self._repo.insert(
            AuditEntry(
                id=None,
                timestamp=datetime.now(tz=UTC),
                event_type=event_type,
                resource_uid=resource.uid if resource else None,
                resource_kind=resource.kind if resource else None,
                resource_name=resource.name if resource else None,
                actor=actor,
                details=details or {},
                trace_id=bound.trace_id,
                conversation_id=bound.conversation_id,
                turn_id=bound.turn_id,
            )
        )
        # Mirror every audited event into the log. Coffer used to log only its
        # failures — a live daemon.log held 4,277 lines of which 62 were
        # Coffer's own, all one error type, and a search for
        # `secret_set`, `agent_mcp_installed`, `provider_switched`,
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
        its uid, not its current label. ``kind`` alone is the coarser filter the
        activity page uses.
        """
        return await self._repo.query(
            kind=kind,
            resource_uid=resource.uid if resource else None,
            event_type=event_type,
            event_prefix=event_prefix,
            since=since,
            limit=limit,
        )

    async def page(
        self,
        *,
        resource: Resource | None = None,
        kind: str | None = None,
        event_type: str | None = None,
        event_prefix: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
        cursor: str | None = None,
        trace_id: str | None = None,
        q: str | None = None,
        q_types: Sequence[str] = (),
    ) -> Page[AuditEntry]:
        """One page of :meth:`query`, newest first, continued by ``cursor``
        (spec resource-framework "Page growing lists by an opaque cursor").

        The cursor is bound to these filters: one issued for another kind or
        another ``since`` is refused ``CURSOR_INVALID`` rather than read as a
        position in an order it was never taken from.
        """
        filters = {
            "kind": kind,
            "resource_uid": resource.uid if resource else None,
            "event_type": event_type,
            "event_prefix": event_prefix,
            "since": since.isoformat() if since else None,
            "trace_id": trace_id,
            "q": q,
            "q_types": sorted(q_types),
        }
        after = time_and_id(decode_cursor(cursor, list_tag="audit", filters=filters), int)
        rows = await self._repo.query(
            kind=kind,
            resource_uid=resource.uid if resource else None,
            event_type=event_type,
            event_prefix=event_prefix,
            since=since,
            limit=limit + 1,
            after=after,
            trace_id=trace_id,
            q=q,
            q_types=q_types,
        )
        return paginate(
            rows,
            limit,
            list_tag="audit",
            filters=filters,
            key=lambda e: position_of(e.timestamp, e.id),
        )

    async def count(
        self,
        *,
        resource: Resource | None = None,
        kind: str | None = None,
        event_type: str | None = None,
        event_prefix: str | None = None,
        since: datetime | None = None,
        trace_id: str | None = None,
        q: str | None = None,
        q_types: Sequence[str] = (),
    ) -> int:
        """How many entries match the filters :meth:`page` takes, across every
        page (spec resource-framework "Count a log's matching rows beside each
        page"). No cursor and no limit: the answer is the same on every page.
        """
        return await self._repo.count(
            kind=kind,
            resource_uid=resource.uid if resource else None,
            event_type=event_type,
            event_prefix=event_prefix,
            since=since,
            trace_id=trace_id,
            q=q,
            q_types=q_types,
        )
