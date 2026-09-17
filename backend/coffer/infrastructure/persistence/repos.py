"""SQLAlchemy concrete implementations of the application-layer repository Protocols."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import sqlalchemy.exc
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.audit import AuditEntry
from coffer.domain.errors import ResourceAlreadyExists, ResourceNotFound
from coffer.domain.internal_engine_config import (
    AGGREGATE,
    CURATE,
    DISTIL,
    GlobalInternalEngineConfig,
    UpkeepSetting,
)
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.scope import Scope
from coffer.infrastructure.persistence.models import (
    AuditLogModel,
    InternalEngineConfigModel,
    ResourceModel,
)
from coffer.infrastructure.persistence.retention_repo import (
    SqlAlchemyRetentionRepo,  # re-export (split out for file-size budget)
)

__all__ = ["SqlAlchemyRetentionRepo"]


def _to_domain(row: ResourceModel) -> Resource:
    return Resource(
        id=row.id,
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

    async def find(self, ref: ResourceRef) -> Resource | None:
        async with self._sm() as session:
            stmt = select(ResourceModel).where(
                ResourceModel.kind == ref.kind,
                ResourceModel.name == ref.name,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_domain(row) if row else None

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
        ref: ResourceRef,
        config: dict[str, Any],
        description: str | None,
    ) -> Resource:
        async with self._sm() as session:
            stmt = select(ResourceModel).where(
                ResourceModel.kind == ref.kind,
                ResourceModel.name == ref.name,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ResourceNotFound(ref.kind, ref.name)
            row.config_json = json.dumps(config)
            row.description = description
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def set_enabled(self, ref: ResourceRef, enabled: bool) -> Resource:
        async with self._sm() as session:
            stmt = select(ResourceModel).where(
                ResourceModel.kind == ref.kind,
                ResourceModel.name == ref.name,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ResourceNotFound(ref.kind, ref.name)
            row.enabled = enabled
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def update_scope(
        self,
        ref: ResourceRef,
        scope: Scope | None,
    ) -> Resource | None:
        async with self._sm() as session:
            stmt = select(ResourceModel).where(
                ResourceModel.kind == ref.kind,
                ResourceModel.name == ref.name,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            row.scope_json = _scope_json(scope)
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def rename(self, ref: ResourceRef, new_name: str) -> Resource:
        """Move a row to ``new_name`` within its kind.

        The (kind, name) unique constraint is the authority on collisions, so a
        racing writer that claimed the name first surfaces as the same
        ``ResourceAlreadyExists`` a caller's own pre-check would have raised —
        never as a raw IntegrityError.
        """
        async with self._sm() as session:
            stmt = select(ResourceModel).where(
                ResourceModel.kind == ref.kind,
                ResourceModel.name == ref.name,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ResourceNotFound(ref.kind, ref.name)
            row.name = new_name
            row.updated_at = datetime.now(tz=UTC)
            try:
                await session.commit()
            except sqlalchemy.exc.IntegrityError as e:
                raise ResourceAlreadyExists(ref.kind, new_name) from e
            await session.refresh(row)
            return _to_domain(row)

    async def delete(self, ref: ResourceRef) -> None:
        async with self._sm() as session:
            stmt = select(ResourceModel).where(
                ResourceModel.kind == ref.kind,
                ResourceModel.name == ref.name,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
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
                # Match the resource by id OR by the label it carries, so a
                # renamed resource's whole trail comes back — including the rows
                # written under its old name, and the rows written before the id
                # column existed.
                label = and_(
                    AuditLogModel.resource_kind == kind,
                    AuditLogModel.resource_name == name,
                )
                stmt = stmt.where(or_(AuditLogModel.resource_id == resource_id, label))
            else:
                if kind is not None:
                    stmt = stmt.where(AuditLogModel.resource_kind == kind)
                if name is not None:
                    stmt = stmt.where(AuditLogModel.resource_name == name)
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


#: Which pair of columns each unattended pass keeps its switch and timer in.
#: One table rather than a branch per pass, so adding a pass is one entry.
_UPKEEP_COLUMNS = {
    AGGREGATE: ("auto_aggregate_enabled", "aggregate_interval_s"),
    DISTIL: ("auto_distil_enabled", "distil_interval_s"),
    CURATE: ("auto_curate_enabled", "curate_interval_s"),
}


class SqlAlchemyInternalEngineConfigRepo:
    """Concrete repo for the singleton ``internal_engine_config`` row."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get(self) -> GlobalInternalEngineConfig | None:
        async with self._sm() as session:
            stmt = select(InternalEngineConfigModel).where(InternalEngineConfigModel.id == 1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            updated = row.updated_at.replace(tzinfo=UTC) if row.updated_at else datetime.now(tz=UTC)
            return self._to_domain(row, updated)

    async def set(
        self,
        *,
        model: str | None,
        curate_owner_machine_id: str | None = None,
        upkeep: Mapping[str, UpkeepSetting] | None = None,
    ) -> GlobalInternalEngineConfig:
        async with self._sm() as session:
            stmt = select(InternalEngineConfigModel).where(InternalEngineConfigModel.id == 1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC)
            if row is None:
                row = InternalEngineConfigModel(id=1, updated_at=now)
                session.add(row)
            row.model = model
            if curate_owner_machine_id is not None:
                # The empty string clears it back to "wherever this is read".
                row.curate_owner_machine_id = curate_owner_machine_id or None
            for name, setting in (upkeep or {}).items():
                enabled_col, interval_col = _UPKEEP_COLUMNS[name]
                setattr(row, enabled_col, setting.enabled)
                setattr(row, interval_col, setting.interval_s)
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row, now)

    async def set_model_timeout(self, seconds: int | None) -> GlobalInternalEngineConfig:
        """Write only the timeout column. ``None`` restores the built-in default."""
        return await self._set_one("model_timeout_s", seconds)

    async def set_transcribe_model(self, model: str | None) -> GlobalInternalEngineConfig:
        """Write only the transcription model. ``None`` stops transcription."""
        return await self._set_one("transcribe_model", model)

    async def _set_one(self, column: str, value: object) -> GlobalInternalEngineConfig:
        """Read-modify-write ONE column of the singleton.

        One column per write rather than a whole-config update: this row
        converges through vault sync, so an update restating fields the caller
        never looked at is a lost update waiting for the moment the operator
        changes two settings on two machines. The same reasoning as
        ``set_upkeep``'s one-pass-per-write.
        """
        async with self._sm() as session:
            stmt = select(InternalEngineConfigModel).where(InternalEngineConfigModel.id == 1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC)
            if row is None:
                row = InternalEngineConfigModel(id=1, updated_at=now)
                session.add(row)
            setattr(row, column, value)
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row, now)

    @staticmethod
    def _to_domain(
        row: InternalEngineConfigModel, updated_at: datetime
    ) -> GlobalInternalEngineConfig:
        return GlobalInternalEngineConfig(
            model=row.model,
            updated_at=updated_at,
            auto_curate_enabled=bool(row.auto_curate_enabled),
            curate_owner_machine_id=row.curate_owner_machine_id,
            auto_aggregate_enabled=bool(row.auto_aggregate_enabled),
            aggregate_interval_s=row.aggregate_interval_s,
            auto_distil_enabled=bool(row.auto_distil_enabled),
            distil_interval_s=row.distil_interval_s,
            curate_interval_s=row.curate_interval_s,
            model_timeout_s=row.model_timeout_s,
            transcribe_model=row.transcribe_model,
        )
