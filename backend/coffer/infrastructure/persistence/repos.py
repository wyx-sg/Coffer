"""SQLAlchemy concrete implementations of the application-layer repository Protocols."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.domain.audit import AuditEntry
from coffer.domain.errors import ResourceAlreadyExists, ResourceNotFound
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from coffer.infrastructure.persistence.internal_engine_repo import (
    SqlAlchemyInternalEngineConfigRepo,  # re-export (split out for file-size budget)
)
from coffer.infrastructure.persistence.models import (
    AuditLogModel,
    ResourceModel,
)
from coffer.infrastructure.persistence.retention_repo import (
    SqlAlchemyRetentionRepo,  # re-export (split out for file-size budget)
)

__all__ = ["SqlAlchemyInternalEngineConfigRepo", "SqlAlchemyRetentionRepo"]


def _to_domain(row: ResourceModel) -> Resource:
    return Resource(
        id=row.id,
        uid=row.uid,
        kind=row.kind,
        name=row.name,
        description=row.description,
        config=json.loads(row.config_json),
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
        scope=Scope.from_json(json.loads(row.scope_json)) if row.scope_json else None,
    )


def _scope_json(scope: Scope | None) -> str | None:
    """The column's text for ``scope``: the agent allow-list object, or NULL."""
    return json.dumps(scope.to_json()) if scope is not None else None


class SqlAlchemyResourceRepo:
    """Concrete ResourceRepo against the `resources` table."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def find(self, uid: str) -> Resource | None:
        async with self._sm() as session:
            row = await self._row(session, uid)
            return _to_domain(row) if row else None

    async def find_by_name(self, kind: str, name: str) -> Resource | None:
        """Resolve a LABEL to a resource — for a human's input, and for the
        within-kind uniqueness check. Never used to carry identity around."""
        async with self._sm() as session:
            stmt = select(ResourceModel).where(
                ResourceModel.kind == kind,
                ResourceModel.name == name,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_domain(row) if row else None

    @staticmethod
    async def _row(session: AsyncSession, uid: str) -> ResourceModel | None:
        stmt = select(ResourceModel).where(ResourceModel.uid == uid)
        row: ResourceModel | None = (await session.execute(stmt)).scalar_one_or_none()
        return row

    async def list(
        self,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[Resource]:
        async with self._sm() as session:
            # Ordered, because the caller renders this as a LIST and the user
            # clicks a row in it. Without an ORDER BY, SQLite is free to hand
            # back whatever order the b-tree scan happens to produce, and an
            # UPDATE can move a row within it: enabling one server made it
            # trade places with another, the refetched list re-rendered in the
            # new order, and the row the user had just clicked was no longer
            # where they clicked it — which reads as "I clicked row 1 and row 4
            # changed". Name is the column a reader scans, and (kind, name) is
            # unique, so the order is total and never depends on a write.
            stmt = select(ResourceModel)
            if kind is not None:
                stmt = stmt.where(ResourceModel.kind == kind)
            if enabled is not None:
                stmt = stmt.where(ResourceModel.enabled == enabled)
            stmt = stmt.order_by(ResourceModel.kind, ResourceModel.name)
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(r) for r in rows]

    async def create(self, resource: Resource) -> Resource:
        async with self._sm() as session:
            row = ResourceModel(
                uid=resource.uid,
                kind=resource.kind,
                name=resource.name,
                description=resource.description,
                config_json=json.dumps(resource.config),
                enabled=resource.enabled,
                created_at=resource.created_at,
                updated_at=resource.updated_at,
                scope_json=_scope_json(resource.scope),
            )
            session.add(row)
            try:
                await session.commit()
            except sqlalchemy.exc.IntegrityError as e:
                raise ResourceAlreadyExists(resource.kind, resource.name) from e
            await session.refresh(row)
            return _to_domain(row)

    async def update_config(
        self,
        uid: str,
        config: dict[str, Any],
        description: str | None,
    ) -> Resource:
        async with self._sm() as session:
            row = await self._row(session, uid)
            if row is None:
                raise ResourceNotFound(uid)
            row.config_json = json.dumps(config)
            row.description = description
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def set_enabled(self, uid: str, enabled: bool) -> Resource:
        async with self._sm() as session:
            row = await self._row(session, uid)
            if row is None:
                raise ResourceNotFound(uid)
            row.enabled = enabled
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def update_scope(
        self,
        uid: str,
        scope: Scope | None,
    ) -> Resource | None:
        async with self._sm() as session:
            row = await self._row(session, uid)
            if row is None:
                return None
            row.scope_json = _scope_json(scope)
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def rename(self, uid: str, new_name: str) -> Resource:
        """Change the row's LABEL. The resource does not move; nothing else
        pointing at it has to be rewritten, because nothing else holds the name.

        The (kind, name) unique constraint is the authority on collisions, so a
        racing writer that claimed the name first surfaces as the same
        ``ResourceAlreadyExists`` a caller's own pre-check would have raised —
        never as a raw IntegrityError.
        """
        async with self._sm() as session:
            row = await self._row(session, uid)
            if row is None:
                raise ResourceNotFound(uid)
            kind = row.kind
            row.name = new_name
            row.updated_at = datetime.now(tz=UTC)
            try:
                await session.commit()
            except sqlalchemy.exc.IntegrityError as e:
                raise ResourceAlreadyExists(kind, new_name) from e
            await session.refresh(row)
            return _to_domain(row)

    async def delete(self, uid: str) -> None:
        async with self._sm() as session:
            row = await self._row(session, uid)
            if row is None:
                return  # idempotent
            await session.delete(row)
            await session.commit()


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
        resource_id=row.resource_id,
        resource_kind=row.resource_kind,
        resource_name=row.resource_name,
        actor=row.actor,
        details=json.loads(row.details_json) if row.details_json else {},
    )


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
                resource_id=entry.resource_id,
                resource_kind=entry.resource_kind,
                resource_name=entry.resource_name,
                actor=entry.actor,
                details_json=json.dumps(entry.details) if entry.details else None,
            )
            session.add(row)
            await session.commit()

    async def query(
        self,
        *,
        kind: str | None = None,
        name: str | None = None,
        resource_id: int | None = None,
        event_type: str | None = None,
        event_prefix: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        async with self._sm() as session:
            stmt = select(AuditLogModel).order_by(AuditLogModel.timestamp.desc())
            if resource_id is not None:
                # By id alone. The old query ORed in "rows carrying this kind
                # and name", which brought back a renamed resource's earlier
                # trail — and, in exactly the same breath, the trail of a
                # DIFFERENT resource that had held the name before being
                # deleted. Two objects' histories rendered as one is a worse
                # answer than a short one, and now that every write records the
                # row's real id there is nothing left for the fallback to
                # rescue except rows written before migration 0067, which are
                # still readable in the unfiltered and kind-filtered views.
                stmt = stmt.where(AuditLogModel.resource_id == resource_id)
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
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_audit_to_domain(r) for r in rows]
