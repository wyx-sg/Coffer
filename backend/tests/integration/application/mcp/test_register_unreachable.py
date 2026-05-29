"""Edge-case coverage: register succeeds for an unreachable upstream.

Per spec edge-case "Upstream unreachable on register": coffer's register
endpoint does not probe the upstream — it stores the config and returns 201.
Discovery is what surfaces the failure.

See specs/001-mcp-gateway/spec.md § Edge Cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)


@pytest.mark.asyncio
async def test_register_succeeds_for_unreachable_upstream(tmp_path: Path) -> None:
    """Register doesn't probe upstreams — an unreachable command should register
    fine.  Discovery is what surfaces the failure (tested separately in
    test_discovery.py).
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    rsvc = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server",
                display_name="MCP Server",
                config_schema=MCPServerConfig,
            )
        },
        repo=repo,
        audit=audit,
    )

    resource = await rsvc.register(
        kind="mcp_server",
        name="ghost",
        config={
            "transport": {
                "type": "stdio",
                "command": "/this/binary/definitely/does/not/exist",
                "args": [],
            },
        },
        actor="test",
    )

    assert resource.name == "ghost"
    assert resource.enabled is True

    await engine.dispose()
