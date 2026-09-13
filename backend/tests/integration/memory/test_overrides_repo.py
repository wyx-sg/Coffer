"""``memory_overrides`` survives a round trip against a real SQLite file
(spec memory FR-040/FR-070).

Mirrors ``backend/tests/integration/sync/test_sync_remote_repo.py``: the
thing under test is precisely that the schema round-trips through real
SQLAlchemy/SQLite, so an in-memory double would only assert our own
assumptions about the ORM.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.memory.overrides import Override
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.memory_overrides_repo import OverrideRepository
from coffer.infrastructure.persistence.models import MemoryOverrideModel


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
    repo = OverrideRepository(sm)
    assert await repo.get("some-fact-key") is None
    assert await repo.all() == {}


async def test_set_then_get_round_trips_every_field(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = OverrideRepository(sm)
    override = Override(
        fact_key="abc123",
        hidden=True,
        pinned=False,
        superseded_by="def456",
        conflict_choice="ghi789",
    )
    await repo.set(override, actor="dev")
    assert await repo.get("abc123") == override


async def test_set_twice_replaces_rather_than_erroring(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = OverrideRepository(sm)
    await repo.set(Override(fact_key="abc123", hidden=True), actor="dev")
    await repo.set(Override(fact_key="abc123", hidden=False, pinned=True), actor="dev")
    got = await repo.get("abc123")
    assert got is not None
    assert got.hidden is False
    assert got.pinned is True


async def test_set_persists_the_actor_on_the_row(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = OverrideRepository(sm)
    await repo.set(Override(fact_key="abc123", hidden=True), actor="wyx-sg")
    async with sm() as session:
        row = (
            await session.execute(
                select(MemoryOverrideModel).where(MemoryOverrideModel.fact_key == "abc123")
            )
        ).scalar_one()
        assert row.actor == "wyx-sg"


async def test_clear_removes_it(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = OverrideRepository(sm)
    await repo.set(Override(fact_key="abc123", pinned=True), actor="dev")
    await repo.clear("abc123")
    assert await repo.get("abc123") is None


async def test_clear_of_an_absent_key_does_not_raise(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = OverrideRepository(sm)
    await repo.clear("never-set")


async def test_all_lists_every_override_by_fact_key(sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
    repo = OverrideRepository(sm)
    await repo.set(Override(fact_key="one", hidden=True), actor="dev")
    await repo.set(Override(fact_key="two", pinned=True), actor="dev")
    all_overrides = await repo.all()
    assert set(all_overrides) == {"one", "two"}
    assert all_overrides["one"].hidden is True
    assert all_overrides["two"].pinned is True
