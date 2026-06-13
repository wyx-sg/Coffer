"""Integration: coffer__search_tools over a real gateway session + fake upstreams."""

from __future__ import annotations

import json
import sys
from contextlib import suppress
from pathlib import Path

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.fixtures.keyring import install_in_memory_keyring

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _stdio_config(*, tools):
    args = [str(_FAKE), "--scenario", "basic", "--tools", *tools]
    return {"transport": {"type": "stdio", "command": sys.executable, "args": args}}


async def _safe_dispose(engine):
    import asyncio as _asyncio

    with suppress(_asyncio.CancelledError, Exception):
        await engine.dispose()


async def _setup(tmp_path, server_configs):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resource_svc = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server", display_name="MCP Server", config_schema=MCPServerConfig
            )
        },
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    for name, cfg in server_configs.items():
        await resource_svc.register(kind="mcp_server", name=name, config=cfg, actor="test")
    supervisor = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    inv_repo = MCPInvocationRepo(sm)
    discovery = CapabilityDiscovery(
        resource_service=resource_svc, supervisor=supervisor, preferences=prefs_repo, audit=audit
    )
    session = MCPGatewaySession(
        session_id="test-session",
        resource_service=resource_svc,
        supervisor=supervisor,
        discovery=discovery,
        preferences=prefs_repo,
        invocations=inv_repo,
    )
    return session, inv_repo, engine


@pytest.mark.asyncio
async def test_tools_list_includes_search_tool(tmp_path, monkeypatch):
    install_in_memory_keyring(monkeypatch)
    session, _inv, engine = await _setup(tmp_path, {"gh": _stdio_config(tools=["create_issue"])})
    try:
        listed = await session.handle_request("tools/list")
        names = {t["name"] for t in listed["tools"]}
        assert "coffer__search_tools" in names
        assert "gh__create_issue" in names
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_search_returns_ranked_upstream_tool(tmp_path, monkeypatch):
    install_in_memory_keyring(monkeypatch)
    session, _inv, engine = await _setup(
        tmp_path,
        {"gh": _stdio_config(tools=["create_issue"]), "fs": _stdio_config(tools=["read_file"])},
    )
    try:
        result = await session.handle_request(
            "tools/call",
            {"name": "coffer__search_tools", "arguments": {"query": "create issue", "top_k": 3}},
        )
        assert result["isError"] is False
        payload = json.loads(result["content"][0]["text"])
        assert payload["tools"]
        assert payload["tools"][0]["name"] == "gh__create_issue"
        assert not payload["tools"][0]["name"].startswith("coffer__")
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_search_empty_query_is_in_band_error(tmp_path, monkeypatch):
    install_in_memory_keyring(monkeypatch)
    session, _inv, engine = await _setup(tmp_path, {"gh": _stdio_config(tools=["create_issue"])})
    try:
        result = await session.handle_request(
            "tools/call", {"name": "coffer__search_tools", "arguments": {"query": ""}}
        )
        assert result["isError"] is True
    finally:
        await session.dispose()
        await _safe_dispose(engine)
