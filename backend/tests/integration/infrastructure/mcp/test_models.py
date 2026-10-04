from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from coffer.infrastructure.mcp.persistence import MCPInvocationModel
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

#: An opaque uuid4 hex, the shape a real resource uid has.
_FS_UID = "aa11bb22cc33dd44ee55ff6677889900"


def _now() -> datetime:
    return datetime.now(tz=UTC)


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
                resource_uid=_FS_UID,
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
