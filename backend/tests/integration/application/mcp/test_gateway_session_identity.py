"""The agent identity a gateway session carries comes from the handshake only.

Spec mcp-gateway, "Take the agent identity from the handshake": the shim reports
the agent's uid once, at ``initialize``. A ``_meta`` carrying only the retired
name-shaped key reports nothing, and a built-in call gets the session's identity
in ``agent`` whatever the client put there — or no ``agent`` at all when the
session reported none.

These drive a real ``MCPGatewaySession`` over a real SQLite-backed
``ResourceService`` and a real fake upstream subprocess.
"""

from __future__ import annotations

import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.domain.scope import Scope
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


class _AgentStub(BaseModel):
    """Just enough of an ``agent`` row for the gateway to resolve a uid to a name."""

    model_config = ConfigDict(extra="allow")


def _stdio(tool: str) -> dict[str, Any]:
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", "--tools", tool],
        }
    }


class _Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.seen: list[dict[str, Any]] = []
        self.sessions: list[MCPGatewaySession] = []

    async def start(self) -> None:
        self.engine = create_async_engine_with_pragmas(
            f"sqlite+aiosqlite:///{self.tmp_path / 'c.db'}"
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = session_maker(self.engine)
        self.rsvc = ResourceService(
            kinds={
                "mcp_server": Kind(
                    name="mcp_server",
                    display_name="MCP Server",
                    config_schema=MCPServerConfig,
                    supports_scope=True,
                ),
                "agent": Kind(name="agent", display_name="Agent", config_schema=_AgentStub),
            },
            repo=SqlAlchemyResourceRepo(sm),
            audit=AuditService(SqlAlchemyAuditRepo(sm)),
        )
        self.prefs = MCPCapabilityPreferenceRepo(sm)
        self.invocations = MCPInvocationRepo(sm)

        async def echo(args: dict[str, Any]) -> dict[str, Any]:
            self.seen.append(dict(args))
            return {"ok": True}

        self.builtin = BuiltinToolRegistry()
        self.builtin.register(
            BuiltinTool(
                name="echo",
                description="records the arguments it was called with",
                input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                handler=echo,
            )
        )

    async def session(self, meta: dict[str, Any]) -> MCPGatewaySession:
        supervisor = SubprocessSupervisor(
            upstream_factory=build_upstream,
            resource_service=self.rsvc,
            credential_resolver=CredentialResolver(KeyringAdapter()),
        )
        session = MCPGatewaySession(
            session_id=f"s{len(self.sessions)}",
            resource_service=self.rsvc,
            supervisor=supervisor,
            discovery=CapabilityDiscovery(
                resource_service=self.rsvc, supervisor=supervisor, preferences=self.prefs
            ),
            preferences=self.prefs,
            invocations=self.invocations,
            builtin_tools=self.builtin,
        )
        self.sessions.append(session)
        await session.handle_initialize({"protocolVersion": "2025-06-18", "_meta": meta})
        return session

    async def close(self) -> None:
        import asyncio

        for s in self.sessions:
            await s.dispose()
        with suppress(asyncio.CancelledError, Exception):
            await self.engine.dispose()


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a name-only handshake is treated as unidentified",
)
@pytest.mark.asyncio
async def test_a_name_only_handshake_sees_only_unscoped_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    h = _Harness(tmp_path)
    await h.start()
    try:
        agent = await h.rsvc.register(kind="agent", name="claude_code", config={}, actor="test")
        await h.rsvc.register(kind="mcp_server", name="fs", config=_stdio("read_file"), actor="t")
        gh = await h.rsvc.register(
            kind="mcp_server", name="gh", config=_stdio("create_issue"), actor="t"
        )
        # Scoped to the agent by uid AND by its name, so a gateway that resolved
        # the retired name-shaped key — either way — would let the session in.
        await h.rsvc.update_scope(gh.uid, Scope(agents=[agent.uid, "claude_code"]), actor="t")

        session = await h.session({"coffer/agent": "claude_code"})
        assert session._session_agent_uid is None

        listed = await session.handle_request("tools/list")
        upstream = {t["name"] for t in listed["tools"] if not t["name"].startswith("coffer__")}
        assert upstream == {"fs__read_file"}

        # Control: the same agent reporting its uid does see the scoped server.
        by_uid = await h.session({"coffer/agent-uid": agent.uid})
        listed = await by_uid.handle_request("tools/list")
        assert "gh__create_issue" in {t["name"] for t in listed["tools"]}
    finally:
        await h.close()


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a built-in tool call carries the session's identity, not the client's",
)
@pytest.mark.asyncio
async def test_a_built_in_call_gets_the_handshake_identity_or_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    h = _Harness(tmp_path)
    await h.start()
    try:
        agent = await h.rsvc.register(kind="agent", name="claude-code", config={}, actor="t")
        await h.rsvc.register(kind="agent", name="codex", config={}, actor="t")

        identified = await h.session({"coffer/agent-uid": agent.uid})
        unidentified = await h.session({})
        call = {"name": "coffer__echo", "arguments": {"text": "hi", "agent": "codex"}}

        await identified.handle_request("tools/call", dict(call, arguments=dict(call["arguments"])))
        await unidentified.handle_request(
            "tools/call", dict(call, arguments=dict(call["arguments"]))
        )

        assert h.seen[0] == {"text": "hi", "agent": "claude-code"}
        assert h.seen[1] == {"text": "hi"}

        # Neither session is offered an ``agent`` to fill in: the gateway threads
        # the identity itself and adds no such property to what it advertises.
        # (Every built-in the real composition root wires is checked the same
        # way in surfaces/http/mcp/test_builtin_tools_advertise_no_agent.py.)
        for session in (identified, unidentified):
            listed = await session.handle_request("tools/list")
            builtins = {t["name"]: t for t in listed["tools"] if t["name"].startswith("coffer__")}
            assert "coffer__echo" in builtins
            for tool in builtins.values():
                schema = tool.get("inputSchema") or {}
                assert "agent" not in schema.get("properties", {}), tool["name"]
                assert "agent" not in schema.get("required", []), tool["name"]
    finally:
        await h.close()
