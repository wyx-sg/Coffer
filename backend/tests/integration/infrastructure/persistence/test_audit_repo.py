from datetime import UTC, datetime, timedelta

import pytest

from coffer.domain.audit import AuditEntry, AuditEventType
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo


def _entry(
    *,
    when: datetime,
    event_type: str = AuditEventType.RESOURCE_CREATED.value,
    kind: str | None = "mcp_server",
    name: str | None = "filesystem",
    actor: str = "cli",
    details: dict | None = None,
) -> AuditEntry:
    return AuditEntry(
        id=None,
        timestamp=when,
        event_type=event_type,
        resource_kind=kind,
        resource_name=name,
        actor=actor,
        details=details if details is not None else {"config": {}},
    )


async def _repo(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlAlchemyAuditRepo(session_maker(engine)), engine


@pytest.mark.asyncio
async def test_insert_then_query(tmp_path):
    repo, engine = await _repo(tmp_path)
    when = datetime(2026, 5, 20, tzinfo=UTC)
    await repo.insert(_entry(when=when))
    rows = await repo.query()
    assert len(rows) == 1
    assert rows[0].event_type == "resource_created"
    assert rows[0].resource_kind == "mcp_server"
    assert rows[0].details == {"config": {}}
    await engine.dispose()


@pytest.mark.asyncio
async def test_query_by_kind_and_name(tmp_path):
    repo, engine = await _repo(tmp_path)
    when = datetime(2026, 5, 20, tzinfo=UTC)
    await repo.insert(_entry(when=when, kind="mcp_server", name="filesystem"))
    await repo.insert(_entry(when=when, kind="mcp_server", name="github"))
    await repo.insert(_entry(when=when, kind="other_kind", name="x"))
    fs_only = await repo.query(kind="mcp_server", name="filesystem")
    assert len(fs_only) == 1
    mcp_all = await repo.query(kind="mcp_server")
    assert len(mcp_all) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_query_by_event_type(tmp_path):
    repo, engine = await _repo(tmp_path)
    when = datetime(2026, 5, 20, tzinfo=UTC)
    await repo.insert(_entry(when=when, event_type="resource_created"))
    await repo.insert(_entry(when=when, event_type="resource_updated"))
    only_created = await repo.query(event_type="resource_created")
    assert len(only_created) == 1
    assert only_created[0].event_type == "resource_created"
    await engine.dispose()


@pytest.mark.asyncio
async def test_query_since(tmp_path):
    repo, engine = await _repo(tmp_path)
    now = datetime(2026, 5, 20, tzinfo=UTC)
    older = now - timedelta(days=10)
    await repo.insert(_entry(when=older))
    await repo.insert(_entry(when=now))
    recent = await repo.query(since=now - timedelta(days=1))
    assert len(recent) == 1
    assert recent[0].timestamp == now
    await engine.dispose()


@pytest.mark.asyncio
async def test_query_limit_and_order(tmp_path):
    """Results come back newest-first."""
    repo, engine = await _repo(tmp_path)
    base = datetime(2026, 5, 20, tzinfo=UTC)
    for i in range(5):
        await repo.insert(_entry(when=base + timedelta(hours=i)))
    rows = await repo.query(limit=3)
    assert len(rows) == 3
    timestamps = [r.timestamp for r in rows]
    assert timestamps == sorted(timestamps, reverse=True)
    await engine.dispose()


@pytest.mark.asyncio
async def test_insert_with_null_resource_fields(tmp_path):
    """Daemon-level events have no resource."""
    repo, engine = await _repo(tmp_path)
    await repo.insert(
        _entry(
            when=datetime(2026, 5, 20, tzinfo=UTC),
            event_type=AuditEventType.DAEMON_STARTED.value,
            kind=None,
            name=None,
            actor="system",
            details={"port": 8000},
        )
    )
    rows = await repo.query()
    assert rows[0].resource_kind is None
    assert rows[0].resource_name is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_insert_with_empty_details(tmp_path):
    repo, engine = await _repo(tmp_path)
    await repo.insert(_entry(when=datetime(2026, 5, 20, tzinfo=UTC), details={}))
    rows = await repo.query()
    assert rows[0].details == {}
    await engine.dispose()
