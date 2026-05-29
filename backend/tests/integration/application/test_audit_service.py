from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo


async def _service(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    return AuditService(SqlAlchemyAuditRepo(sm)), engine


@pytest.mark.asyncio
async def test_record_with_resource_ref(tmp_path):
    svc, engine = await _service(tmp_path)
    await svc.record(
        AuditEventType.RESOURCE_CREATED.value,
        ref=ResourceRef("mcp_server", "filesystem"),
        actor="cli",
        details={"config": {"transport": "stdio"}},
    )
    entries = await svc.query()
    assert len(entries) == 1
    e = entries[0]
    assert e.event_type == "resource_created"
    assert e.resource_kind == "mcp_server"
    assert e.resource_name == "filesystem"
    assert e.actor == "cli"
    assert e.details == {"config": {"transport": "stdio"}}
    assert e.timestamp is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_record_without_ref_uses_system_actor_default(tmp_path):
    """Daemon-level events default to actor='system' and have no resource ref."""
    svc, engine = await _service(tmp_path)
    await svc.record(AuditEventType.DAEMON_STARTED.value, details={"port": 8000})
    entries = await svc.query()
    assert entries[0].resource_kind is None
    assert entries[0].resource_name is None
    assert entries[0].actor == "system"
    assert entries[0].details == {"port": 8000}
    await engine.dispose()


@pytest.mark.asyncio
async def test_record_empty_details_default(tmp_path):
    svc, engine = await _service(tmp_path)
    await svc.record("resource_enabled", ref=ResourceRef("mcp_server", "x"), actor="api")
    entries = await svc.query()
    assert entries[0].details == {}
    await engine.dispose()


@pytest.mark.asyncio
async def test_query_filters(tmp_path):
    svc, engine = await _service(tmp_path)
    await svc.record("resource_created", ref=ResourceRef("mcp_server", "a"), actor="cli")
    await svc.record("resource_created", ref=ResourceRef("mcp_server", "b"), actor="cli")
    await svc.record("resource_updated", ref=ResourceRef("mcp_server", "a"), actor="api")

    only_a = await svc.query(name="a")
    assert len(only_a) == 2

    only_created = await svc.query(event_type="resource_created")
    assert len(only_created) == 2

    only_a_created = await svc.query(name="a", event_type="resource_created")
    assert len(only_a_created) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_query_since(tmp_path):
    svc, engine = await _service(tmp_path)
    await svc.record("resource_created", ref=ResourceRef("mcp_server", "old"), actor="cli")
    # All entries arrive ~now; querying since `now + 1 hour` should yield none
    recent = await svc.query(since=datetime.now(tz=UTC) + timedelta(hours=1))
    assert recent == []
    await engine.dispose()
