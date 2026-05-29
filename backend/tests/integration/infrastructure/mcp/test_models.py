from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceModel,
    MCPInvocationModel,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.models import ResourceModel


def _now() -> datetime:
    return datetime.now(tz=UTC)


@pytest.mark.asyncio
async def test_capability_preference_round_trip(tmp_path):
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
        await s.flush()
        s.add(
            MCPCapabilityPreferenceModel(
                resource_id=r.id,
                capability_type="tool",
                capability_key="read_file",
                enabled=True,
                first_seen_at=_now(),
                last_seen_at=_now(),
            )
        )
        await s.commit()
    async with sm() as s:
        row = (await s.execute(select(MCPCapabilityPreferenceModel))).scalar_one()
    assert row.capability_key == "read_file"
    await engine.dispose()


@pytest.mark.asyncio
async def test_preference_cascade_on_resource_delete(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    async with sm() as s:
        r = ResourceModel(
            kind="mcp_server",
            name="fs",
            description=None,
            config_json="{}",
            enabled=True,
            created_at=_now(),
            updated_at=_now(),
        )
        s.add(r)
        await s.flush()
        s.add(
            MCPCapabilityPreferenceModel(
                resource_id=r.id,
                capability_type="tool",
                capability_key="x",
                enabled=True,
                first_seen_at=_now(),
                last_seen_at=_now(),
            )
        )
        await s.commit()
        await s.delete(r)
        await s.commit()
    async with sm() as s:
        rows = (await s.execute(select(MCPCapabilityPreferenceModel))).scalars().all()
    assert rows == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_preference_unique_constraint(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    import sqlalchemy.exc

    async with sm() as s:
        r = ResourceModel(
            kind="mcp_server",
            name="fs",
            description=None,
            config_json="{}",
            enabled=True,
            created_at=_now(),
            updated_at=_now(),
        )
        s.add(r)
        await s.flush()
        s.add(
            MCPCapabilityPreferenceModel(
                resource_id=r.id,
                capability_type="tool",
                capability_key="x",
                enabled=True,
                first_seen_at=_now(),
                last_seen_at=_now(),
            )
        )
        await s.commit()
        s.add(
            MCPCapabilityPreferenceModel(
                resource_id=r.id,
                capability_type="tool",
                capability_key="x",
                enabled=False,
                first_seen_at=_now(),
                last_seen_at=_now(),
            )
        )
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_invocation_round_trip(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    async with sm() as s:
        s.add(
            MCPInvocationModel(
                timestamp=_now(),
                resource_name="filesystem",
                capability_type="tool",
                capability_key="read_file",
                duration_ms=42,
                status="ok",
                error_message=None,
                session_id="sess-1",
            )
        )
        await s.commit()
    async with sm() as s:
        row = (await s.execute(select(MCPInvocationModel))).scalar_one()
    assert row.duration_ms == 42
    assert row.status == "ok"
    await engine.dispose()
