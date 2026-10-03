"""A key the upstream rejects in a real call reaches the server's health.

A minimal raw-socket HTTP MCP upstream answers ``initialize`` and ``tools/list``
and takes a switch for ``tools/call``: 401 (a revoked key), a result with
``isError``, or an ordinary result. The gateway forwards calls to it with the
real supervisor and the real HTTP upstream connection.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp.attention import McpAttentionSource
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.mcp.upstream_auth import UpstreamAuthMonitor
from coffer.application.resource_service import ResourceService
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceStore,
    MCPInvocationRepo,
    MCPServerHealthRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter
from tests.fixtures.keyring import install_in_memory_keyring
from tests.support.vault_stores import derived_sm, make_resource_repo


class _Upstream:
    """``tool_call`` is what ``tools/call`` answers: ``401``, ``is_error`` or ``ok``."""

    def __init__(self) -> None:
        self.tool_call = "ok"
        self.port = 0

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            lines = head.decode().split("\r\n")
            headers = {
                k.lower(): v.strip() for k, _, v in (ln.partition(":") for ln in lines[1:] if ln)
            }
            body = await reader.readexactly(int(headers.get("content-length", "0")))
            if not lines[0].startswith("POST"):
                writer.write(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n")
            else:
                writer.write(self._answer(json.loads(body)))
            await writer.drain()
        finally:
            writer.close()

    def _answer(self, msg: dict[str, Any]) -> bytes:
        method = msg.get("method")
        if "id" not in msg:
            return b"HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        if method == "tools/call" and self.tool_call == "401":
            return b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        result: dict[str, Any] = {}
        if method == "initialize":
            result = {
                "protocolVersion": msg["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "raw", "version": "1"},
            }
        elif method == "tools/call":
            result = {
                "content": [{"type": "text", "text": "x"}],
                "isError": self.tool_call == "is_error",
            }
        elif method == "tools/list":
            result = {"tools": []}
        payload = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}).encode()
        return (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n"
            + f"Content-Length: {len(payload)}\r\n\r\n".encode()
            + payload
        )


@pytest.fixture
async def upstream() -> AsyncIterator[_Upstream]:
    up = _Upstream()
    server = await asyncio.start_server(up._serve, "127.0.0.1", 0)
    up.port = server.sockets[0].getsockname()[1]
    try:
        yield up
    finally:
        server.close()
        await server.wait_closed()


async def _build(tmp_path: Path, up: _Upstream, monkeypatch: pytest.MonkeyPatch) -> Any:
    install_in_memory_keyring(monkeypatch)
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    rsvc = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server",
                display_name="MCP Server",
                config_schema=MCPServerConfig,
                supports_scope=True,
            )
        },
        repo=make_resource_repo(home=tmp_path),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    server = await rsvc.register(
        kind="mcp_server",
        name="remote",
        config={"transport": {"type": "http", "url": f"http://127.0.0.1:{up.port}/mcp"}},
        actor="test",
    )
    supervisor = SubprocessSupervisor(
        resource_service=rsvc,
        secret_resolver=SecretResolver(KeyringAdapter()),
        upstream_factory=build_upstream,
        retry_delays=(),
    )
    prefs = MCPCapabilityPreferenceStore(derived_sm())
    health = MCPServerHealthRepo(derived_sm())
    monitor = UpstreamAuthMonitor(health)
    nudges: list[int] = []
    monitor.on_change = lambda: nudges.append(1)
    session = MCPGatewaySession(
        session_id="s",
        resource_service=rsvc,
        supervisor=supervisor,
        discovery=CapabilityDiscovery(
            resource_service=rsvc, supervisor=supervisor, preferences=prefs
        ),
        preferences=prefs,
        invocations=MCPInvocationRepo(sm),
        auth_monitor=monitor,
    )
    return session, rsvc, server.uid, health, nudges, engine


async def _call(session: MCPGatewaySession) -> dict[str, Any]:
    return await session.handle_request("tools/call", {"name": "remote__echo", "arguments": {}})


class _Secrets:
    def exists(self, ref: str) -> bool:
        return True


async def _items(rsvc: ResourceService, health: MCPServerHealthRepo) -> list[str]:
    source = McpAttentionSource(resources=rsvc, health=health, secrets=_Secrets())
    return [i.reason_code for i in await source.items()]


async def _teardown(session: MCPGatewaySession, engine: Any) -> None:
    await session.dispose()
    with suppress(asyncio.CancelledError, Exception):
        await engine.dispose()


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a rejected key from a real call reaches the Overview"
)
async def test_a_401_on_a_tool_call_records_auth_rejected_and_the_overview_lists_it(
    tmp_path: Path, upstream: _Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, rsvc, uid, health, nudges, engine = await _build(tmp_path, upstream, monkeypatch)
    try:
        assert await _call(session)  # a first answered call: nothing to record
        assert await health.get(uid) is None
        upstream.tool_call = "401"
        with pytest.raises(UpstreamUnavailable):
            await _call(session)
        row = await health.get(uid)
        assert row is not None and row[0] == "failing"
        assert await health.get_reason(uid) == "auth_rejected"
        assert nudges
        assert await _items(rsvc, health) == ["mcp_key_rejected"]

        # The key is replaced upstream: the next answered call clears it.
        upstream.tool_call = "ok"
        await _call(session)
        row = await health.get(uid)
        assert row is not None and row[0] == "healthy"
        assert await _items(rsvc, health) == []
    finally:
        await _teardown(session, engine)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool error result does not mark a server failing"
)
async def test_an_is_error_result_leaves_health_alone(
    tmp_path: Path, upstream: _Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, _rsvc, uid, health, nudges, engine = await _build(tmp_path, upstream, monkeypatch)
    try:
        upstream.tool_call = "is_error"
        result = await _call(session)
        assert result["isError"] is True
        assert await health.get(uid) is None
        assert nudges == []
    finally:
        await _teardown(session, engine)
