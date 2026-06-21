"""Integration tests for the DistilledSessionRepo idempotency ledger (007 FR-046)."""

from datetime import UTC, datetime

from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.distilled_session_repo import DistilledSessionRepo
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)


async def _repo(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return DistilledSessionRepo(session_maker(engine)), engine


async def test_mark_then_is_distilled_roundtrip(tmp_path):
    repo, engine = await _repo(tmp_path)
    sha = "a" * 64
    assert await repo.is_distilled("claude_code", "s1", sha) is False
    await repo.mark_distilled("claude_code", "s1", sha, datetime.now(tz=UTC))
    assert await repo.is_distilled("claude_code", "s1", sha) is True
    await engine.dispose()


async def test_is_distilled_discriminates_by_sha(tmp_path):
    repo, engine = await _repo(tmp_path)
    await repo.mark_distilled("claude_code", "s1", "old-sha", datetime.now(tz=UTC))
    # Same agent + session but new content sha → not yet distilled (re-distill).
    assert await repo.is_distilled("claude_code", "s1", "old-sha") is True
    assert await repo.is_distilled("claude_code", "s1", "new-sha") is False
    await engine.dispose()


async def test_is_distilled_discriminates_by_agent_and_session(tmp_path):
    repo, engine = await _repo(tmp_path)
    sha = "shared-sha"
    await repo.mark_distilled("claude_code", "s1", sha, datetime.now(tz=UTC))
    assert await repo.is_distilled("codex", "s1", sha) is False
    assert await repo.is_distilled("claude_code", "s2", sha) is False
    await engine.dispose()


async def test_duplicate_mark_is_a_noop(tmp_path):
    repo, engine = await _repo(tmp_path)
    sha = "dup-sha"
    when = datetime.now(tz=UTC)
    await repo.mark_distilled("claude_code", "s1", sha, when)
    # A second identical mark must not raise on the unique constraint.
    await repo.mark_distilled("claude_code", "s1", sha, when)
    assert await repo.is_distilled("claude_code", "s1", sha) is True
    await engine.dispose()
