# backend/tests/integration/infrastructure/persistence/test_retention_repo.py
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from coffer.infrastructure.chat import (
    persistence as _chat_persistence,  # noqa: F401 (registers chat tables on Base.metadata)
)
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
async def test_delete_older_than_conversations_cascades_to_messages(tmp_path):
    """Pruning old conversations also removes their messages (no orphan rows)."""
    from sqlalchemy import text

    repo, engine = await _repo(tmp_path)
    sm = session_maker(engine)
    now = datetime(2026, 5, 20, tzinfo=UTC)
    old = now - timedelta(days=40)
    recent = now - timedelta(days=1)

    async with sm() as s:
        # One stale thread (2 messages) and one recent thread (1 message).
        conv_sql = (
            "INSERT INTO conversations "
            "(id, agent_key, title, model_id, created_at, updated_at) "
            "VALUES (:id, 'builtin', 't', NULL, :ts, :ts)"
        )
        msg_sql = (
            "INSERT INTO chat_messages "
            "(id, conversation_id, seq, role, content, status, created_at) "
            "VALUES (:id, :cid, :seq, 'user', '[]', 'complete', :ts)"
        )
        for cid, ts, nmsg in [("old", old, 2), ("new", recent, 1)]:
            await s.execute(text(conv_sql), {"id": cid, "ts": ts})
            for seq in range(nmsg):
                await s.execute(
                    text(msg_sql),
                    {"id": f"{cid}-{seq}", "cid": cid, "seq": seq, "ts": ts},
                )
        await s.commit()

    cutoff = now - timedelta(days=7)
    deleted = await repo.delete_older_than("conversations", "updated_at", cutoff)
    assert deleted == 1  # only the stale conversation

    async with sm() as s:
        convs = (await s.execute(text("SELECT id FROM conversations"))).scalars().all()
        msgs = (await s.execute(text("SELECT conversation_id FROM chat_messages"))).scalars().all()
    assert set(convs) == {"new"}
    # The stale thread's messages are gone; the recent thread's remain.
    assert set(msgs) == {"new"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_archive_older_than_stamps_idle_threads_only(tmp_path):
    """archive_older_than sets archived_at on idle, not-yet-archived rows only."""
    from sqlalchemy import text

    repo, engine = await _repo(tmp_path)
    sm = session_maker(engine)
    now = datetime(2026, 5, 20, tzinfo=UTC)
    idle = now - timedelta(days=10)
    active = now - timedelta(days=1)

    conv_sql = (
        "INSERT INTO conversations "
        "(id, agent_key, title, model_id, created_at, updated_at, archived_at) "
        "VALUES (:id, 'builtin', 't', NULL, :ts, :ts, :arch)"
    )
    async with sm() as s:
        await s.execute(text(conv_sql), {"id": "idle", "ts": idle, "arch": None})
        await s.execute(text(conv_sql), {"id": "active", "ts": active, "arch": None})
        # Already archived long ago — must not be re-stamped.
        await s.execute(text(conv_sql), {"id": "done", "ts": idle, "arch": idle})
        await s.commit()

    cutoff = now - timedelta(days=7)
    affected = await repo.archive_older_than(
        "conversations", "updated_at", "archived_at", cutoff, now
    )
    assert affected == 1  # only the idle, not-yet-archived thread

    async with sm() as s:
        rows = dict((await s.execute(text("SELECT id, archived_at FROM conversations"))).all())
    assert rows["idle"] is not None  # newly archived
    assert rows["active"] is None  # too recent, untouched
    # Pre-existing archived_at preserved (its original date, not re-stamped to now).
    # Raw text() reads the column back as a string, so compare on the date prefix.
    assert str(rows["done"]).startswith("2026-05-10")
    await engine.dispose()


@pytest.mark.asyncio
async def test_archive_older_than_rejects_unlisted_columns(tmp_path):
    repo, engine = await _repo(tmp_path)
    with pytest.raises(UnknownPrunableTable):
        await repo.archive_older_than(
            "conversations", "updated_at", "title", datetime.now(tz=UTC), datetime.now(tz=UTC)
        )
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
