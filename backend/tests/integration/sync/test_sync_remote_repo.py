"""The single-row backup-remote config survives a round-trip (spec vault-export-import).

Against a real SQLite file rather than a fake repo: the thing under test is
precisely that the schema holds one row and that every field comes back as it
went in, and an in-memory double would only assert our own assumptions about
SQLAlchemy.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.sync.backup import BackupRemote, BackupRun, BackupRunStatus
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.sync_remote_repo import SqlAlchemySyncRemoteRepo


@pytest.fixture
async def sm(tmp_path: pathlib.Path) -> AsyncIterator[async_sessionmaker]:  # type: ignore[type-arg]
    """A fresh empty vault database per test."""
    db = tmp_path / "coffer.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield session_maker(engine)
    finally:
        await engine.dispose()


async def test_absent_until_set(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    assert await repo.get() is None
    assert await repo.last_run() is None


async def test_set_then_get_round_trips_every_field(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    remote = BackupRemote(
        url="https://example.invalid/vault.git",
        branch="backup",
        credential_ref="sync.BACKUP_TOKEN",
        include_credentials=True,
        interval_seconds=900,
        enabled=True,
        worktree_path="~/.coffer/sync",
    )
    await repo.set(remote)
    assert await repo.get() == remote


async def test_set_twice_keeps_one_row(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/one.git"))
    await repo.set(BackupRemote(url="https://example.invalid/two.git"))
    got = await repo.get()
    assert got is not None
    assert got.url == "https://example.invalid/two.git"


async def test_clear_removes_it(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    await repo.clear()
    assert await repo.get() is None


async def test_record_run_is_readable_back(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = SqlAlchemySyncRemoteRepo(sm)
    await repo.set(BackupRemote(url="https://example.invalid/vault.git"))
    await repo.record_run(
        BackupRun(
            status=BackupRunStatus.PUSH_FAILED,
            commit="abc1234",
            error="offline",
            ran_at=datetime(2026, 9, 12, tzinfo=UTC),
        )
    )
    run = await repo.last_run()
    assert run is not None
    assert run.status is BackupRunStatus.PUSH_FAILED
    assert run.commit == "abc1234"
    assert run.error == "offline"
