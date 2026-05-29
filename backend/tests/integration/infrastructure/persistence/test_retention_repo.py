# backend/tests/integration/infrastructure/persistence/test_retention_repo.py
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.models import AuditLogModel
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyRetentionRepo,
    UnknownPrunableTable,
)


async def _repo(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlAlchemyRetentionRepo(session_maker(engine)), engine


@pytest.mark.asyncio
async def test_upsert_and_get(tmp_path):
    repo, engine = await _repo(tmp_path)
    await repo.upsert("audit_log", 365)
    p = await repo.get("audit_log")
    assert p.table_name == "audit_log"
    assert p.retention_days == 365
    assert p.last_pruned_rows == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_idempotent(tmp_path):
    """upsert overwrites; calling twice doesn't error."""
    repo, engine = await _repo(tmp_path)
    await repo.upsert("audit_log", 365)
    await repo.upsert("audit_log", 30)
    p = await repo.get("audit_log")
    assert p.retention_days == 30
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_missing_raises(tmp_path):
    repo, engine = await _repo(tmp_path)
    with pytest.raises(UnknownPrunableTable):
        await repo.get("never_added")
    await engine.dispose()


@pytest.mark.asyncio
async def test_list(tmp_path):
    repo, engine = await _repo(tmp_path)
    await repo.upsert("audit_log", 365)
    await repo.upsert("mcp_invocations", 30)
    rows = await repo.list()
    assert {r.table_name for r in rows} == {"audit_log", "mcp_invocations"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_retention(tmp_path):
    repo, engine = await _repo(tmp_path)
    await repo.upsert("audit_log", 365)
    await repo.update_retention("audit_log", 180)
    assert (await repo.get("audit_log")).retention_days == 180
    await repo.update_retention("audit_log", None)
    assert (await repo.get("audit_log")).retention_days is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_touch_pruned(tmp_path):
    repo, engine = await _repo(tmp_path)
    await repo.upsert("audit_log", 365)
    await repo.touch_pruned("audit_log", 42)
    p = await repo.get("audit_log")
    assert p.last_pruned_rows == 42
    assert p.last_pruned_at is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_exists(tmp_path):
    repo, engine = await _repo(tmp_path)
    assert (await repo.exists("audit_log")) is False
    await repo.upsert("audit_log", 365)
    assert (await repo.exists("audit_log")) is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_older_than_basic(tmp_path):
    """Delete audit_log rows older than a cutoff."""
    repo, engine = await _repo(tmp_path)
    sm = session_maker(engine)
    now = datetime(2026, 5, 20, tzinfo=UTC)
    async with sm() as s:
        for i in range(5):
            s.add(
                AuditLogModel(
                    timestamp=now - timedelta(days=i),
                    event_type="resource_created",
                    resource_kind="mcp_server",
                    resource_name=f"r{i}",
                    actor="cli",
                    details_json=None,
                )
            )
        await s.commit()

    cutoff = now - timedelta(days=2)
    deleted = await repo.delete_older_than("audit_log", "timestamp", cutoff)
    # Two rows had timestamps < cutoff (i=3 and i=4)
    assert deleted == 2

    async with sm() as s:
        remaining = (await s.execute(select(func.count()).select_from(AuditLogModel))).scalar_one()
    assert remaining == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_older_than_rejects_unknown_table(tmp_path):
    """SQL injection guard: only allow-listed tables can be pruned."""
    repo, engine = await _repo(tmp_path)
    with pytest.raises(UnknownPrunableTable):
        await repo.delete_older_than("nope_table", "timestamp", datetime.now(tz=UTC))
    # Even more dangerous payloads must be rejected
    with pytest.raises(UnknownPrunableTable):
        await repo.delete_older_than(
            "audit_log; DROP TABLE resources; --",
            "timestamp",
            datetime.now(tz=UTC),
        )
    with pytest.raises(UnknownPrunableTable):
        await repo.delete_older_than("audit_log", "junk_column", datetime.now(tz=UTC))
    await engine.dispose()
