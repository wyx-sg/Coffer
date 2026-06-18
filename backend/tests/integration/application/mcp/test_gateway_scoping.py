"""Integration tests for per-agent MCP server scoping at the gateway (ADR-026).

Mirrors the harness in ``test_gateway.py`` (real ``ResourceService`` + real
SQLite + a fake upstream subprocess) but additionally injects a fake
``AgentMcpScopePort`` and binds an agent identity, so the four 001-mcp-gateway
scoping scenarios are exercised end-to-end through ``MCPGatewaySession``.

The fake scope object maps an agent name to its allowlist: ``None`` ==
unscoped (auto / unknown agent), a ``set[str]`` == selected mode.
"""

from __future__ import annotations

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
from coffer.domain.scope_errors import AgentMcpServerNotInScope
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


async def _safe_dispose(engine: object) -> None:
    import asyncio as _asyncio

    with suppress(_asyncio.CancelledError, Exception):
        await engine.dispose()  # type: ignore[union-attr]


def _stdio_config(*, tools: list[str]) -> dict:  # type: ignore[type-arg]
    args = [str(_FAKE), "--scenario", "basic", "--tools", *tools]
    return {"transport": {"type": "stdio", "command": sys.executable, "args": args}}


class _FakeScope:
    """Satisfies AgentMcpScopePort: agent name -> allowlist (set) or None."""

    def __init__(self, mapping: dict[str, set[str] | None]) -> None:
        self._mapping = mapping

    async def allowed_server_names(self, agent_name: str) -> set[str] | None:
        return self._mapping.get(agent_name)


async def _setup(
    tmp_path: Path,
    server_configs: dict[str, dict],  # type: ignore[type-arg]
    *,
    scope: _FakeScope | None = None,
) -> tuple[MCPGatewaySession, object]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resource_svc = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server",
                display_name="MCP Server",
                config_schema=MCPServerConfig,
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
        resource_service=resource_svc,
        supervisor=supervisor,
        preferences=prefs_repo,
        audit=audit,
    )
    session = MCPGatewaySession(
        session_id="scope-session",
        resource_service=resource_svc,
        supervisor=supervisor,
        discovery=discovery,
        preferences=prefs_repo,
        invocations=inv_repo,
        scope=scope,  # type: ignore[arg-type]
    )
    return session, engine


def _upstream_tool_names(result: dict) -> set[str]:  # type: ignore[type-arg]
    return {t["name"] for t in result["tools"] if not t["name"].startswith("coffer__")}


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="scope an agent to a subset of servers")
@pytest.mark.asyncio
async def test_selected_scope_hides_out_of_scope_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    session, engine = await _setup(
        tmp_path,
        {"a": _stdio_config(tools=["a_tool"]), "b": _stdio_config(tools=["b_tool"])},
        scope=_FakeScope({"agentA": {"a"}}),
    )
    session.bind_agent("agentA")
    try:
        result = await session.handle_request("tools/list")
        names = _upstream_tool_names(result)
        assert names == {"a__a_tool"}, names
        assert "b__b_tool" not in names
        # Builtins (incl. search_tools) are still present and unaffected.
        assert any(t["name"].startswith("coffer__") for t in result["tools"])
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="reject an out-of-scope tool call")
@pytest.mark.asyncio
async def test_selected_scope_rejects_out_of_scope_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    session, engine = await _setup(
        tmp_path,
        {"a": _stdio_config(tools=["a_tool"]), "b": _stdio_config(tools=["b_tool"])},
        scope=_FakeScope({"agentA": {"a"}}),
    )
    session.bind_agent("agentA")
    try:
        # Naming server B's tool directly must be rejected before B is spawned.
        with pytest.raises(AgentMcpServerNotInScope) as exc:
            await session.handle_request("tools/call", {"name": "b__b_tool", "arguments": {}})
        assert exc.value.server_name == "b"
        # The rejection is recorded as a denied invocation (security observability).
        denied = await session._invocations.query(resource_name="b")
        assert any(inv.status == "denied" and inv.capability_key == "b_tool" for inv in denied)
        # The in-scope server A is still callable.
        ok = await session.handle_request("tools/call", {"name": "a__a_tool", "arguments": {}})
        assert "content" in ok
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="auto-mode agent sees all enabled servers")
@pytest.mark.asyncio
async def test_auto_mode_agent_sees_all_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    # auto mode -> allowed_server_names returns None for this agent.
    session, engine = await _setup(
        tmp_path,
        {"a": _stdio_config(tools=["a_tool"]), "b": _stdio_config(tools=["b_tool"])},
        scope=_FakeScope({"agentA": None}),
    )
    session.bind_agent("agentA")
    try:
        result = await session.handle_request("tools/list")
        assert _upstream_tool_names(result) == {"a__a_tool", "b__b_tool"}
        # And a direct call to either server is allowed.
        ok = await session.handle_request("tools/call", {"name": "b__b_tool", "arguments": {}})
        assert "content" in ok
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="an anonymous session is unscoped")
@pytest.mark.asyncio
async def test_anonymous_session_is_unscoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    # A scope object exists, but the session never binds an agent -> unscoped.
    session, engine = await _setup(
        tmp_path,
        {"a": _stdio_config(tools=["a_tool"]), "b": _stdio_config(tools=["b_tool"])},
        scope=_FakeScope({"agentA": {"a"}}),
    )
    # NOTE: no session.bind_agent(...) call.
    try:
        result = await session.handle_request("tools/list")
        assert _upstream_tool_names(result) == {"a__a_tool", "b__b_tool"}
        # An anonymous session can call any enabled server's tool.
        ok = await session.handle_request("tools/call", {"name": "b__b_tool", "arguments": {}})
        assert "content" in ok
    finally:
        await session.dispose()
        await _safe_dispose(engine)
