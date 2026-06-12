"""SQLAlchemy concrete implementations of the application-layer repository Protocols."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.audit import AuditEntry
from coffer.domain.embedding_config import SINGLETON_ID, GlobalEmbeddingConfig
from coffer.domain.errors import ResourceAlreadyExists, ResourceNotFound
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.persistence.models import (
    AuditLogModel,
    EmbeddingConfigModel,
    ResourceModel,
)
from coffer.infrastructure.persistence.retention import UnknownPrunableTable  # re-export
from coffer.infrastructure.persistence.retention_repo import (
    SqlAlchemyRetentionRepo,  # re-export (split out for file-size budget)
)

__all__ = ["SqlAlchemyRetentionRepo", "UnknownPrunableTable"]


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


def _embedding_to_domain(row: EmbeddingConfigModel) -> GlobalEmbeddingConfig:
    return GlobalEmbeddingConfig(
        enabled=bool(row.enabled),
        provider=row.provider,
        model=row.model,
        base_url=row.base_url,
        credential_ref=row.credential_ref,
        dimensions=row.dimensions,
        default_chunk_size=row.default_chunk_size,
        default_chunk_overlap=row.default_chunk_overlap,
        updated_at=row.updated_at.replace(tzinfo=UTC) if row.updated_at else datetime.now(tz=UTC),
    )


class SqlAlchemyEmbeddingConfigRepo:
    """Concrete repo for the singleton ``embedding_config`` row."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get(self) -> GlobalEmbeddingConfig | None:
        async with self._sm() as session:
            stmt = select(EmbeddingConfigModel).where(EmbeddingConfigModel.id == SINGLETON_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _embedding_to_domain(row) if row is not None else None

    async def set(
        self,
        *,
        enabled: bool,
        provider: str | None,
        model: str | None,
        base_url: str | None,
        credential_ref: str | None,
        dimensions: int,
        default_chunk_size: int,
        default_chunk_overlap: int,
    ) -> GlobalEmbeddingConfig:
        async with self._sm() as session:
            stmt = select(EmbeddingConfigModel).where(EmbeddingConfigModel.id == SINGLETON_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC)
            if row is None:
                row = EmbeddingConfigModel(id=SINGLETON_ID, updated_at=now)
                session.add(row)
            row.enabled = enabled
            row.provider = provider
            row.model = model
            row.base_url = base_url
            row.credential_ref = credential_ref
            row.dimensions = dimensions
            row.default_chunk_size = default_chunk_size
            row.default_chunk_overlap = default_chunk_overlap
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return _embedding_to_domain(row)
