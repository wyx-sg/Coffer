"""Integration tests for the sync_config / sync_state singleton repos."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.domain.sync.models import SyncState, SyncStatus
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.sync.persistence import (
    SqlAlchemySyncConfigRepo,
    SqlAlchemySyncStateRepo,
)


@pytest_asyncio.fixture
async def sm(tmp_path):  # type: ignore[no-untyped-def]
    engine: AsyncEngine = create_async_engine_with_pragmas(
        f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield session_maker(engine)
    await engine.dispose()


async def test_config_defaults_to_none_then_round_trips(sm) -> None:  # type: ignore[no-untyped-def]
    repo = SqlAlchemySyncConfigRepo(sm)
    assert await repo.get() is None

    saved = await repo.set(
        remote="git@github.com:me/vault.git",
        enabled=True,
        auto=True,
        interval_seconds=120,
        branch="main",
    )
    assert saved.remote == "git@github.com:me/vault.git"
    assert saved.enabled is True
    assert saved.auto is True
    assert saved.interval_seconds == 120

    again = await repo.get()
    assert again is not None
    assert again.is_operational()


async def test_config_set_is_idempotent_single_row(sm) -> None:  # type: ignore[no-untyped-def]
    repo = SqlAlchemySyncConfigRepo(sm)
    await repo.set(remote="a", enabled=True, auto=False, interval_seconds=300, branch="main")
    await repo.set(remote="b", enabled=False, auto=False, interval_seconds=300, branch="dev")
    got = await repo.get()
    assert got is not None
    assert got.remote == "b"
    assert got.branch == "dev"
    assert got.enabled is False


async def test_state_round_trips_lists(sm) -> None:  # type: ignore[no-untyped-def]
    repo = SqlAlchemySyncStateRepo(sm)
    assert await repo.get() is None

    await repo.set(
        SyncState(
            status=SyncStatus.CONFLICTED,
            last_sync_at=None,
            last_error=None,
            conflict_paths=["resources/mcp_server/x.yaml", "memory/global/a.md"],
            locked_refs=["cred-1"],
        )
    )
    got = await repo.get()
    assert got is not None
    assert got.status is SyncStatus.CONFLICTED
    assert got.conflict_paths == ["resources/mcp_server/x.yaml", "memory/global/a.md"]
    assert got.locked_refs == ["cred-1"]


@pytest.mark.acceptance(spec="010-sync", scenario="only shared state syncs")
async def test_state_persists_clean_status(sm) -> None:  # type: ignore[no-untyped-def]
    repo = SqlAlchemySyncStateRepo(sm)
    await repo.set(SyncState(status=SyncStatus.CLEAN, last_sync_at=None, last_error=None))
    got = await repo.get()
    assert got is not None
    assert got.status is SyncStatus.CLEAN
    assert got.conflict_paths == []
