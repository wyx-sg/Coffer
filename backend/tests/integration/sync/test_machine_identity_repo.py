"""The machine-identity singleton repo against real SQLite (ADR-043).

Pins the first-use race guard: two overlapping creates must converge on ONE
machine id — the loser adopts the winner's identity instead of raising.
"""

from __future__ import annotations

from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.sync.persistence import SqlAlchemyMachineIdentityRepo


async def _repo(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlAlchemyMachineIdentityRepo(session_maker(engine)), engine


async def test_double_create_converges_on_one_identity(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    try:
        winner = await repo.create("01AAAAAAAAAAAAAAAAAAAAAAAA", "first")
        loser = await repo.create("01BBBBBBBBBBBBBBBBBBBBBBBB", "second")
        assert loser == winner  # the machine id never forks
        stored = await repo.get()
        assert stored == winner
    finally:
        await engine.dispose()


async def test_rename_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    try:
        created = await repo.create("01AAAAAAAAAAAAAAAAAAAAAAAA", "host")
        renamed = await repo.set_display_name("studio")
        assert renamed.machine_id == created.machine_id
        assert (await repo.get()) == renamed
    finally:
        await engine.dispose()
