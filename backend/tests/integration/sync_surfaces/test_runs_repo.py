"""Rounds in ``runs.db`` (``sync_runs``): newest first, paged, by id."""

from __future__ import annotations

from pathlib import Path

from coffer.domain.sync.rounds import AppliedChange, PulledCommit, RoundRecord, RoundStatus
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.sync_runs_repo import SyncRunRepo


def _round(i: int, status: RoundStatus = RoundStatus.PULLED) -> RoundRecord:
    return RoundRecord(
        status=status,
        started_at=f"2026-09-30T08:0{i}:00+00:00",
        finished_at=f"2026-09-30T08:0{i}:30+00:00",
        to_commit=f"c{i}",
        pulled=(PulledCommit("c", "2026-09-30T07:00:00+00:00", "Mac", 2),),
        applied=(AppliedChange("knowledge/a.md", "added"),),
        detail="git said no" if status is RoundStatus.PUSH_FAILED else None,
    )


async def test_rounds_are_stored_and_read_back_newest_first(tmp_path: Path) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repo = SyncRunRepo(session_maker(engine))
    first = await repo.append(_round(1))
    second = await repo.append(_round(2, RoundStatus.PUSH_FAILED))
    assert first.id is not None and second.id == first.id + 1
    assert [r.id for r in await repo.recent(10)] == [second.id, first.id]
    assert [r.id for r in await repo.recent(1, offset=1)] == [first.id]
    got = await repo.get(second.id)  # type: ignore[arg-type]
    assert got == second
    assert got is not None and got.pulled[0].machine == "Mac" and got.detail == "git said no"
    assert await repo.get(999) is None
    assert await repo.count() == 2
    await engine.dispose()
