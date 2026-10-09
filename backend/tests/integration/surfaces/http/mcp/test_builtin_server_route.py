"""GET /api/v1/mcp/builtin — Coffer's own ``coffer`` server, described read-only.

Spec mcp-gateway "Describe the built-in coffer server". Real SQLite for the
invocation log and a real built-in call recorded through the gateway's own
dispatch; the connected-agents source is the composition root's, exercised
separately against fake agent services.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.mcp.gateway_builtin import dispatch_builtin_tool
from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.surfaces.http import daemon_port
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.builtin_server_wiring import wire_builtin_server
from coffer.surfaces.http.mcp import builtin_routes
from coffer.surfaces.http.mcp.builtin_routes import BuiltinServerSource, get_builtin_server_source
from coffer.surfaces.http.mcp.dependencies import get_invocation_repo


async def _write(_args: dict[str, Any]) -> dict[str, Any]:
    return {"written": True}


def _registry() -> BuiltinToolRegistry:
    reg = BuiltinToolRegistry()
    reg.register(
        BuiltinTool(
            name="write",
            description="File a durable fact about this environment.",
            input_schema={"type": "object", "properties": {}},
            handler=_write,
        )
    )
    return reg


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the built-in coffer server is described read-only"
)
@pytest.mark.asyncio
async def test_the_builtin_coffer_server_is_described_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    invocations = MCPInvocationRepo(session_maker(engine))
    registry = _registry()
    await dispatch_builtin_tool(
        prefixed_name="coffer__write",
        params={"arguments": {}},
        builtin=registry,
        invocations=invocations,
        session_id="s1",
        clock=lambda: datetime.now(tz=UTC),
        session_agent_uid="agent-1",
    )

    async def _connected() -> list[str]:
        return ["agent-1"]

    monkeypatch.setattr(daemon_port, "_PORT", 8123)
    set_active_token("tok")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(builtin_routes.router)
    app.dependency_overrides[get_builtin_server_source] = lambda: BuiltinServerSource(
        registry, _connected
    )
    app.dependency_overrides[get_invocation_repo] = lambda: invocations
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t", headers={"X-Coffer-Token": "tok"}
        ) as client:
            r = await client.get("/api/v1/mcp/builtin")
    finally:
        await engine.dispose()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "coffer"
    assert body["url"] == "http://127.0.0.1:8123/mcp"
    assert body["transport"] == "http"
    assert body["status"] == "healthy"
    assert body["connected_agent_uids"] == ["agent-1"]
    assert [(t["name"], t["qualified_name"]) for t in body["tools"]] == [
        ("search_tools", "coffer__search_tools"),
        ("write", "coffer__write"),
    ]
    assert body["tool_count"] == 2
    # Each carries its input schema, for the row's details.
    assert body["tools"][1]["input_schema"] == {"type": "object", "properties": {}}
    assert "properties" in body["tools"][0]["input_schema"]
    summary = body["summary"]
    assert (summary["calls"], summary["errors"]) == (1, 0)
    assert summary["by_agent"][0]["agent_uid"] == "agent-1"
    assert summary["by_tool"][0]["tool"] == "write"
    assert body["invocation_uid"] == "coffer"


class _Agent:
    def __init__(self, uid: str) -> None:
        self.uid = uid


class _Agents:
    async def list(self) -> list[_Agent]:
        return [_Agent("a"), _Agent("b"), _Agent("c")]


class _Status:
    def __init__(self, installed: bool) -> None:
        self.installed = installed


class _Connections:
    async def status(self, uid: str) -> _Status:
        if uid == "c":
            raise ValueError("no MCP config for this type")
        return _Status(uid == "a")


@pytest.mark.asyncio
async def test_connected_agents_are_those_whose_config_holds_coffers_entry() -> None:
    wire_builtin_server(_registry(), _Agents(), _Connections())  # type: ignore[arg-type]
    try:
        assert await get_builtin_server_source().connected_agents() == ["a"]
    finally:
        builtin_routes.set_builtin_server_source(None)
