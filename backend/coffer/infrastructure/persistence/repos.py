"""SQLAlchemy concrete implementations of the application-layer repository Protocols."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy.exc
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.audit import AuditEntry
from coffer.domain.errors import ResourceAlreadyExists, ResourceNotFound
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.retention import RetentionPolicy
from coffer.infrastructure.persistence.models import (
    AuditLogModel,
    ResourceModel,
    RetentionPolicyModel,
)
from coffer.infrastructure.persistence.retention import UnknownPrunableTable  # re-export

__all__ = ["UnknownPrunableTable"]


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
    )


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
            stmt = select(ResourceModel)
            if kind is not None:
                stmt = stmt.where(ResourceModel.kind == kind)
            if enabled is not None:
                stmt = stmt.where(ResourceModel.enabled == enabled)
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
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        async with self._sm() as session:
            stmt = select(AuditLogModel).order_by(AuditLogModel.timestamp.desc())
            if kind is not None:
                stmt = stmt.where(AuditLogModel.resource_kind == kind)
            if name is not None:
                stmt = stmt.where(AuditLogModel.resource_name == name)
            if event_type is not None:
                stmt = stmt.where(AuditLogModel.event_type == event_type)
            if since is not None:
                stmt = stmt.where(AuditLogModel.timestamp >= since)
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_audit_to_domain(r) for r in rows]


# === SqlAlchemyRetentionRepo (T024) ===


# Allowlists for delete_older_than. The keys are tables that may be pruned;
# the values are the only timestamp-column names allowed for that table.
# These are populated by the application layer through registration; for
# now, the kind-agnostic core seeds the audit_log entry, and Phase 3 will
# add `mcp_invocations`.
_PRUNABLE_TABLE_ALLOWLIST: dict[str, set[str]] = {
    "audit_log": {"timestamp"},
    "mcp_invocations": {"timestamp"},
}


def _retention_to_domain(row: RetentionPolicyModel) -> RetentionPolicy:
    return RetentionPolicy(
        table_name=row.table_name,
        retention_days=row.retention_days,
        last_pruned_at=row.last_pruned_at.replace(tzinfo=UTC)
        if row.last_pruned_at is not None
        else None,
        last_pruned_rows=row.last_pruned_rows,
        updated_at=row.updated_at.replace(tzinfo=UTC) if row.updated_at else datetime.now(tz=UTC),
    )


class SqlAlchemyRetentionRepo:
    """Concrete RetentionRepo against the `retention_policies` table.

    `delete_older_than` validates table+column against
    `_PRUNABLE_TABLE_ALLOWLIST` before constructing any SQL. Never accepts
    user-supplied table names — only values registered at composition root.
    """

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get(self, table_name: str) -> RetentionPolicy:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise UnknownPrunableTable(f"no retention policy registered for {table_name!r}")
            return _retention_to_domain(row)

    async def list(self) -> list[RetentionPolicy]:
        async with self._sm() as session:
            rows = (await session.execute(select(RetentionPolicyModel))).scalars().all()
            return [_retention_to_domain(r) for r in rows]

    async def upsert(self, table_name: str, retention_days: int | None) -> None:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC)
            if row is None:
                session.add(
                    RetentionPolicyModel(
                        table_name=table_name,
                        retention_days=retention_days,
                        last_pruned_at=None,
                        last_pruned_rows=0,
                        updated_at=now,
                    )
                )
            else:
                row.retention_days = retention_days
                row.updated_at = now
            await session.commit()

    async def update_retention(self, table_name: str, retention_days: int | None) -> None:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise UnknownPrunableTable(f"no retention policy registered for {table_name!r}")
            row.retention_days = retention_days
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def touch_pruned(self, table_name: str, rows: int) -> None:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise UnknownPrunableTable(f"no retention policy registered for {table_name!r}")
            row.last_pruned_at = datetime.now(tz=UTC)
            row.last_pruned_rows = rows
            await session.commit()

    async def delete_older_than(
        self,
        table: str,
        timestamp_column: str,
        cutoff: datetime,
    ) -> int:
        allowed_columns = _PRUNABLE_TABLE_ALLOWLIST.get(table)
        if allowed_columns is None or timestamp_column not in allowed_columns:
            raise UnknownPrunableTable(
                f"table/column not in allowlist: ({table!r}, {timestamp_column!r})"
            )
        async with self._sm() as session:
            stmt = text(f"DELETE FROM {table} WHERE {timestamp_column} < :cutoff")
            result = await session.execute(stmt, {"cutoff": cutoff})
            await session.commit()
            return int(result.rowcount or 0)

    async def exists(self, table_name: str) -> bool:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return row is not None
