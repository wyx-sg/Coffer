from datetime import UTC, datetime, timedelta

import pytest

from coffer.domain.mcp.capability import MCPInvocation
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.models import ResourceModel


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _setup(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    async with sm() as s:
        r = ResourceModel(
            kind="mcp_server",
            name="filesystem",
            description=None,
            config_json="{}",
            enabled=True,
            created_at=_now(),
            updated_at=_now(),
        )
        s.add(r)
        await s.commit()
        rid = r.id
    return MCPCapabilityPreferenceRepo(sm), MCPInvocationRepo(sm), rid, engine


@pytest.mark.asyncio
async def test_preference_insert_find_set_enabled(tmp_path):
    pref_repo, _, rid, engine = await _setup(tmp_path)
    await pref_repo.insert(
        resource_id=rid,
        capability_type="tool",
        capability_key="read_file",
        enabled=True,
        first_seen_at=_now(),
        last_seen_at=_now(),
    )
    found = await pref_repo.find(rid, "tool", "read_file")
    assert found is not None
    assert found.enabled is True
    updated = await pref_repo.set_enabled(rid, "tool", "read_file", False)
    assert updated is not None
    assert updated.enabled is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_preference_list_for(tmp_path):
    pref_repo, _, rid, engine = await _setup(tmp_path)
    for k in ("read_file", "write_file", "list_directory"):
        await pref_repo.insert(
            resource_id=rid,
            capability_type="tool",
            capability_key=k,
            enabled=True,
            first_seen_at=_now(),
            last_seen_at=_now(),
        )
    await pref_repo.insert(
        resource_id=rid,
        capability_type="prompt",
        capability_key="summarise",
        enabled=True,
        first_seen_at=_now(),
        last_seen_at=_now(),
    )
    tools = await pref_repo.list_for(rid, "tool")
    assert {p.capability_key for p in tools} == {"read_file", "write_file", "list_directory"}
    everything = await pref_repo.list_for(rid)
    assert len(everything) == 4
    await engine.dispose()


@pytest.mark.asyncio
async def test_preference_touch_last_seen(tmp_path):
    pref_repo, _, rid, engine = await _setup(tmp_path)
    initial = _now() - timedelta(days=2)
    await pref_repo.insert(
        resource_id=rid,
        capability_type="tool",
        capability_key="read_file",
        enabled=True,
        first_seen_at=initial,
        last_seen_at=initial,
    )
    later = _now()
    await pref_repo.touch_last_seen(rid, "tool", "read_file", later)
    p = await pref_repo.find(rid, "tool", "read_file")
    assert p is not None
    assert p.last_seen_at >= initial
    await engine.dispose()


@pytest.mark.asyncio
async def test_invocation_insert_and_query(tmp_path):
    _, inv_repo, _, engine = await _setup(tmp_path)
    base = datetime(2026, 5, 20, tzinfo=UTC)
    for i in range(5):
        await inv_repo.insert(
            MCPInvocation(
                id=None,
                timestamp=base + timedelta(seconds=i),
                resource_name="filesystem",
                capability_type="tool",
                capability_key="read_file",
                duration_ms=10 + i,
                status="ok" if i % 2 == 0 else "error",
                error_message=None if i % 2 == 0 else "boom",
                session_id=None,
            )
        )
    rows = await inv_repo.query(resource_name="filesystem")
    assert len(rows) == 5
    # Newest first
    assert rows[0].duration_ms == 14
    only_ok = await inv_repo.query(resource_name="filesystem", status="ok")
    assert len(only_ok) == 3
    await engine.dispose()
