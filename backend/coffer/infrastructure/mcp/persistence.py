"""MCP-kind ORM models + repos.

Models register against the shared ``Base.metadata`` so Alembic finds them
in one place. Per Contract 5 (cross-kind imports forbidden), this module
must NOT import from any other kind module.

Historically this file held every MCP-side model and repo. To keep
individual modules under the 400-line guideline, the invocation log and
the server-health record now live in sibling modules:

* :mod:`coffer.infrastructure.mcp.invocation_writer` — buffered writer
  repo + ``MCPInvocationModel``.
* :mod:`coffer.infrastructure.mcp.health_repo` — health upsert/query repo
  + ``MCPServerHealthModel``.

This module remains the canonical import point: it re-exports the
public names from those modules so existing call sites (``from
coffer.infrastructure.mcp.persistence import …``) keep working without
edits.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.mcp.capability import (
    CapabilityType,
    MCPCapabilityPreference,
)
from coffer.infrastructure.mcp.health_repo import (
    HealthStatus,
    MCPServerHealthModel,
    MCPServerHealthRepo,
)
from coffer.infrastructure.mcp.invocation_writer import (
    MCPInvocationModel,
    MCPInvocationRepo,
)
from coffer.infrastructure.persistence.base import Base

__all__ = [
    "HealthStatus",
    "MCPCapabilityPreferenceModel",
    "MCPCapabilityPreferenceRepo",
    "MCPInvocationModel",
    "MCPInvocationRepo",
    "MCPServerHealthModel",
    "MCPServerHealthRepo",
]


class MCPCapabilityPreferenceModel(Base):
    __tablename__ = "mcp_capability_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    capability_type: Mapped[str] = mapped_column(String, nullable=False)
    capability_key: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "capability_type",
            "capability_key",
            name="uq_mcp_prefs_resource_type_key",
        ),
        Index(
            "idx_prefs_resource",
            "resource_id",
            "capability_type",
            "enabled",
        ),
    )


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _pref_to_domain(row: MCPCapabilityPreferenceModel) -> MCPCapabilityPreference:
    return MCPCapabilityPreference(
        id=row.id,
        resource_id=row.resource_id,
        capability_type=row.capability_type,  # type: ignore[arg-type]
        capability_key=row.capability_key,
        enabled=row.enabled,
        first_seen_at=_tz(row.first_seen_at),
        last_seen_at=_tz(row.last_seen_at),
    )


class MCPCapabilityPreferenceRepo:
    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def find(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
    ) -> MCPCapabilityPreference | None:
        async with self._sm() as session:
            stmt = select(MCPCapabilityPreferenceModel).where(
                MCPCapabilityPreferenceModel.resource_id == resource_id,
                MCPCapabilityPreferenceModel.capability_type == capability_type,
                MCPCapabilityPreferenceModel.capability_key == capability_key,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _pref_to_domain(row) if row else None

    async def list_for(
        self,
        resource_id: int,
        capability_type: CapabilityType | None = None,
    ) -> list[MCPCapabilityPreference]:
        async with self._sm() as session:
            stmt = select(MCPCapabilityPreferenceModel).where(
                MCPCapabilityPreferenceModel.resource_id == resource_id
            )
            if capability_type is not None:
                stmt = stmt.where(MCPCapabilityPreferenceModel.capability_type == capability_type)
            rows = (await session.execute(stmt)).scalars().all()
            return [_pref_to_domain(r) for r in rows]

    async def insert(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> MCPCapabilityPreference:
        async with self._sm() as session:
            row = MCPCapabilityPreferenceModel(
                resource_id=resource_id,
                capability_type=capability_type,
                capability_key=capability_key,
                enabled=enabled,
                first_seen_at=first_seen_at,
                last_seen_at=last_seen_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _pref_to_domain(row)

    async def set_enabled(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
    ) -> MCPCapabilityPreference | None:
        async with self._sm() as session:
            stmt = select(MCPCapabilityPreferenceModel).where(
                MCPCapabilityPreferenceModel.resource_id == resource_id,
                MCPCapabilityPreferenceModel.capability_type == capability_type,
                MCPCapabilityPreferenceModel.capability_key == capability_key,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            row.enabled = enabled
            await session.commit()
            await session.refresh(row)
            return _pref_to_domain(row)

    async def touch_last_seen(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        when: datetime,
    ) -> None:
        async with self._sm() as session:
            stmt = select(MCPCapabilityPreferenceModel).where(
                MCPCapabilityPreferenceModel.resource_id == resource_id,
                MCPCapabilityPreferenceModel.capability_type == capability_type,
                MCPCapabilityPreferenceModel.capability_key == capability_key,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return
            row.last_seen_at = when
            await session.commit()

    async def reconcile(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        current_keys: list[str],
        *,
        default_enabled: bool,
        when: datetime,
    ) -> list[str]:
        """Insert new keys + touch last_seen for existing keys in one session.

        Returns the list of keys that were newly inserted (so the caller can
        emit one audit row per genuinely-new capability). Race-safe via
        ``INSERT … ON CONFLICT DO NOTHING``: two concurrent reconcile() calls
        from independent sessions cannot both insert the same row, so the
        UniqueConstraint never fires (CODE-004).
        """
        if not current_keys:
            return []
        async with self._sm() as session:
            # Step 1: find which of `current_keys` already exist for this
            # (resource_id, capability_type). One query instead of N.
            existing_stmt = select(MCPCapabilityPreferenceModel.capability_key).where(
                MCPCapabilityPreferenceModel.resource_id == resource_id,
                MCPCapabilityPreferenceModel.capability_type == capability_type,
                MCPCapabilityPreferenceModel.capability_key.in_(current_keys),
            )
            existing_keys = set((await session.execute(existing_stmt)).scalars().all())

            # Step 2: batch UPDATE last_seen_at for existing rows.
            if existing_keys:
                await session.execute(
                    update(MCPCapabilityPreferenceModel)
                    .where(
                        MCPCapabilityPreferenceModel.resource_id == resource_id,
                        MCPCapabilityPreferenceModel.capability_type == capability_type,
                        MCPCapabilityPreferenceModel.capability_key.in_(existing_keys),
                    )
                    .values(last_seen_at=when)
                )

            # Step 3: INSERT … ON CONFLICT DO NOTHING for net-new keys.
            new_keys = [k for k in current_keys if k not in existing_keys]
            if new_keys:
                payload = [
                    {
                        "resource_id": resource_id,
                        "capability_type": capability_type,
                        "capability_key": key,
                        "enabled": default_enabled,
                        "first_seen_at": when,
                        "last_seen_at": when,
                    }
                    for key in new_keys
                ]
                await session.execute(
                    sqlite_insert(MCPCapabilityPreferenceModel)
                    .values(payload)
                    .on_conflict_do_nothing(
                        index_elements=[
                            "resource_id",
                            "capability_type",
                            "capability_key",
                        ],
                    )
                )

            await session.commit()
            return new_keys
