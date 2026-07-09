"""Sync singleton ORM models + repos (sync_config, sync_state).

Both are single-row tables keyed by ``SINGLETON_ID`` (the embedding_config
pattern). ``conflict_paths`` / ``locked_refs`` are JSON-encoded text. No
secrets are stored: git auth is the user's ambient git configuration.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.sync.models import (
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    SINGLETON_ID,
    MachineIdentity,
    SyncConfig,
    SyncState,
    SyncStatus,
)
from coffer.infrastructure.persistence.base import Base


class SyncConfigModel(Base):
    __tablename__ = "sync_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    remote: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_INTERVAL_SECONDS
    )
    branch: Mapped[str] = mapped_column(String, nullable=False, default=DEFAULT_BRANCH)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class SyncStateModel(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=SyncStatus.UNCONFIGURED)
    last_sync_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_paths_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    locked_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class MachineIdentityModel(Base):
    """This machine's stable identity (one row, ``id`` = 1; ADR-043).

    Machine-local state *about* the machine — never exported as vault data."""

    __tablename__ = "machine_identity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    machine_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_machine_identity_singleton"),)


def _config_to_domain(row: SyncConfigModel) -> SyncConfig:
    return SyncConfig(
        remote=row.remote,
        enabled=bool(row.enabled),
        auto=bool(row.auto),
        interval_seconds=row.interval_seconds,
        branch=row.branch,
        updated_at=datetime.fromisoformat(row.updated_at),
    )


def _state_to_domain(row: SyncStateModel) -> SyncState:
    return SyncState(
        status=SyncStatus(row.status),
        last_sync_at=datetime.fromisoformat(row.last_sync_at) if row.last_sync_at else None,
        last_error=row.last_error,
        conflict_paths=list(json.loads(row.conflict_paths_json)),
        locked_refs=list(json.loads(row.locked_refs_json)),
        updated_at=datetime.fromisoformat(row.updated_at),
    )


class SqlAlchemySyncConfigRepo:
    """Concrete repo for the singleton ``sync_config`` row."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get(self) -> SyncConfig | None:
        async with self._sm() as session:
            stmt = select(SyncConfigModel).where(SyncConfigModel.id == SINGLETON_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _config_to_domain(row) if row is not None else None

    async def set(
        self,
        *,
        remote: str | None,
        enabled: bool,
        auto: bool,
        interval_seconds: int,
        branch: str,
    ) -> SyncConfig:
        async with self._sm() as session:
            stmt = select(SyncConfigModel).where(SyncConfigModel.id == SINGLETON_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC).isoformat()
            if row is None:
                row = SyncConfigModel(id=SINGLETON_ID, updated_at=now)
                session.add(row)
            row.remote = remote
            row.enabled = enabled
            row.auto = auto
            row.interval_seconds = interval_seconds
            row.branch = branch
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return _config_to_domain(row)


class SqlAlchemyMachineIdentityRepo:
    """Concrete repo for the singleton ``machine_identity`` row."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get(self) -> MachineIdentity | None:
        async with self._sm() as session:
            stmt = select(MachineIdentityModel).where(MachineIdentityModel.id == SINGLETON_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return MachineIdentity(machine_id=row.machine_id, display_name=row.display_name)

    async def create(self, machine_id: str, display_name: str) -> MachineIdentity:
        try:
            async with self._sm() as session:
                now = datetime.now(tz=UTC).isoformat()
                row = MachineIdentityModel(
                    id=SINGLETON_ID,
                    machine_id=machine_id,
                    display_name=display_name,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.commit()
                return MachineIdentity(machine_id=machine_id, display_name=display_name)
        except IntegrityError:
            # Two overlapping first-use calls both saw no row; the loser keeps
            # the winner's identity — the machine id must never fork.
            existing = await self.get()
            assert existing is not None
            return existing

    async def set_display_name(self, display_name: str) -> MachineIdentity:
        async with self._sm() as session:
            stmt = select(MachineIdentityModel).where(MachineIdentityModel.id == SINGLETON_ID)
            row = (await session.execute(stmt)).scalar_one()
            row.display_name = display_name
            row.updated_at = datetime.now(tz=UTC).isoformat()
            await session.commit()
            return MachineIdentity(machine_id=row.machine_id, display_name=row.display_name)


class SqlAlchemySyncStateRepo:
    """Concrete repo for the singleton ``sync_state`` row."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get(self) -> SyncState | None:
        async with self._sm() as session:
            stmt = select(SyncStateModel).where(SyncStateModel.id == SINGLETON_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _state_to_domain(row) if row is not None else None

    async def set(self, state: SyncState) -> SyncState:
        async with self._sm() as session:
            stmt = select(SyncStateModel).where(SyncStateModel.id == SINGLETON_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC).isoformat()
            if row is None:
                row = SyncStateModel(id=SINGLETON_ID, updated_at=now)
                session.add(row)
            row.status = state.status.value
            row.last_sync_at = state.last_sync_at.isoformat() if state.last_sync_at else None
            row.last_error = state.last_error
            row.conflict_paths_json = json.dumps(state.conflict_paths)
            row.locked_refs_json = json.dumps(state.locked_refs)
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return _state_to_domain(row)
