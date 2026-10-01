"""The audit log repository, over ``runs.db``.

Resources are files (``coffer.infrastructure.vault.resource_store``), the
retention policies local JSON (``retention_repo``) and the engine settings a
vault document (``internal_engine_repo``); what stays here is history.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.audit import AuditEntry
from coffer.infrastructure.persistence.keyset import newest_first_after
from coffer.infrastructure.persistence.models import AuditLogModel

# === SqlAlchemyAuditRepo (T023) ===


def _audit_to_domain(row: AuditLogModel) -> AuditEntry:
    ts = row.timestamp
    # SQLite stores timestamps without tzinfo; re-attach UTC so callers always
    # receive an aware datetime.
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return AuditEntry(
        id=row.id,
        timestamp=ts,
        event_type=row.event_type,
        resource_uid=row.resource_uid,
        resource_kind=row.resource_kind,
        resource_name=row.resource_name,
        actor=row.actor,
        details=json.loads(row.details_json) if row.details_json else {},
        trace_id=row.trace_id,
        conversation_id=row.conversation_id,
        turn_id=row.turn_id,
    )


def _audit_filtered(
    stmt: Select[Any],
    *,
    kind: str | None,
    resource_uid: str | None,
    event_type: str | None,
    event_prefix: str | None,
    since: datetime | None,
    trace_id: str | None = None,
) -> Select[Any]:
    """The one WHERE both an audit page and its count read, so they cannot disagree."""
    if trace_id is not None:
        stmt = stmt.where(AuditLogModel.trace_id == trace_id)
    if resource_uid is not None:
        # By uid alone: filtering by label would render a renamed resource's
        # trail and the trail of a deleted one that once held the name as one.
        stmt = stmt.where(AuditLogModel.resource_uid == resource_uid)
    elif kind is not None:
        stmt = stmt.where(AuditLogModel.resource_kind == kind)
    if event_type is not None:
        stmt = stmt.where(AuditLogModel.event_type == event_type)
    if event_prefix is not None:
        # A feature's whole trail, not one event of it: memory's acts
        # span two kinds (its own partitions, and the agent config a
        # hook install writes), so "everything memory did" cannot be
        # expressed as a kind filter. Filtering here rather than in the
        # caller keeps the page's log complete — a client-side filter
        # over a fixed window silently drops whatever fell outside it.
        stmt = stmt.where(AuditLogModel.event_type.startswith(event_prefix))
    if since is not None:
        stmt = stmt.where(AuditLogModel.timestamp >= since)
    return stmt


class SqlAlchemyAuditRepo:
    """Concrete AuditRepo against the `audit_log` table.

    Query results come back newest-first; the caller controls limit.
    """

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def insert(self, entry: AuditEntry) -> None:
        async with self._sm() as session:
            row = AuditLogModel(
                timestamp=entry.timestamp,
                event_type=entry.event_type,
                resource_uid=entry.resource_uid,
                resource_kind=entry.resource_kind,
                resource_name=entry.resource_name,
                actor=entry.actor,
                details_json=json.dumps(entry.details) if entry.details else None,
                trace_id=entry.trace_id,
                conversation_id=entry.conversation_id,
                turn_id=entry.turn_id,
            )
            session.add(row)
            await session.commit()

    async def query(
        self,
        *,
        kind: str | None = None,
        name: str | None = None,
        resource_uid: str | None = None,
        event_type: str | None = None,
        event_prefix: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
        after: tuple[datetime, int] | None = None,
        trace_id: str | None = None,
    ) -> list[AuditEntry]:
        async with self._sm() as session:
            # Newest first with the id as the tie-break, so ``after`` (the last
            # row of the page before) names one place in the order.
            stmt = select(AuditLogModel).order_by(
                AuditLogModel.timestamp.desc(), AuditLogModel.id.desc()
            )
            if after is not None:
                stmt = stmt.where(
                    newest_first_after(AuditLogModel.timestamp, AuditLogModel.id, after)
                )
            stmt = _audit_filtered(
                stmt,
                kind=kind,
                resource_uid=resource_uid,
                event_type=event_type,
                event_prefix=event_prefix,
                since=since,
                trace_id=trace_id,
            )
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_audit_to_domain(r) for r in rows]

    async def count(
        self,
        *,
        kind: str | None = None,
        resource_uid: str | None = None,
        event_type: str | None = None,
        event_prefix: str | None = None,
        since: datetime | None = None,
        trace_id: str | None = None,
    ) -> int:
        """How many rows :meth:`query` would page through with these filters."""
        async with self._sm() as session:
            stmt = _audit_filtered(
                select(func.count()).select_from(AuditLogModel),
                kind=kind,
                resource_uid=resource_uid,
                event_type=event_type,
                event_prefix=event_prefix,
                since=since,
                trace_id=trace_id,
            )
            return int((await session.execute(stmt)).scalar_one())
