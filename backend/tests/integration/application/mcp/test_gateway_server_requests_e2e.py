"""Sampling and roots relayed through real upstreams, over stdio and HTTP.

Spec mcp-gateway "Relay an upstream's sampling and roots requests to the
client". The upstream is a real MCP server process that asks the client
something in the middle of a tool call (``tests/fixtures/server_requests_mcp_server.py``);
the gateway session spawns it with the real SDK, so the test covers what the
callback-only tests never did: the SDK client session must have the callbacks
when it is constructed. Each downstream "client" here is the session's sink,
answering every server-initiated request the way a client posts its response.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp import gateway_aggregate_lists
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore, MCPInvocationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter
from tests.fixtures.keyring import install_in_memory_keyring
from tests.support.vault_stores import derived_sm, make_resource_repo

pytestmark = pytest.mark.timeout(90)

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "server_requests_mcp_server.py"
_BOTH = {"sampling": {}, "roots": {"listChanged": True}}


@pytest.fixture
def http_upstream(tmp_path: Path) -> Iterator[str]:
    ready = tmp_path / "port"
    proc = subprocess.Popen(
        [sys.executable, str(_FIXTURE), "--transport", "http", "--ready", str(ready)]
    )
    try:
        deadline = time.monotonic() + 30
        while not ready.exists() or not ready.read_text():
            assert proc.poll() is None, "the HTTP upstream exited"
            assert time.monotonic() < deadline, "the HTTP upstream did not start"
            time.sleep(0.05)
        yield f"http://127.0.0.1:{ready.read_text()}/mcp"
    finally:
        proc.terminate()
        with suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)


class _Client:
    """One downstream client: a gateway session plus what it was asked."""

    def __init__(self, session: MCPGatewaySession, answer: str, root: str) -> None:
        self.session = session
        self.asked: list[str] = []
        self._answer, self._root = answer, root
        session.set_downstream_sink(self._sink)

    async def _sink(self, payload: dict[str, Any]) -> None:
        method = payload.get("method")
        if "id" not in payload or method is None:
            return
        self.asked.append(method)
        result: dict[str, Any] = (
            {"role": "assistant", "content": {"type": "text", "text": self._answer}, "model": "m"}
            if method == "sampling/createMessage"
            else {"roots": [{"uri": self._root}]}
        )
        assert self.session.handle_response_from_downstream(
            {"jsonrpc": "2.0", "id": payload["id"], "result": result}
        )

    async def call(self, tool: str) -> tuple[str, bool]:
        out = await self.session.handle_request("tools/call", {"name": tool, "arguments": {}})
        return out["content"][0]["text"], bool(out.get("isError"))


@pytest.fixture
async def gateway(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    install_in_memory_keyring(monkeypatch)
    monkeypatch.setattr(gateway_aggregate_lists, "PER_SERVER_LIST_TIMEOUT", 60.0)
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    resources = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server", display_name="MCP Server", config_schema=MCPServerConfig
            )
        },
        repo=make_resource_repo(home=tmp_path),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    prefs, invocations = MCPCapabilityPreferenceStore(derived_sm()), MCPInvocationRepo(sm)
    sessions: list[MCPGatewaySession] = []

    async def client(caps: dict[str, Any], answer: str = "", root: str = "") -> _Client:
        supervisor = SubprocessSupervisor(
            resource_service=resources,
            secret_resolver=SecretResolver(KeyringAdapter()),
            upstream_factory=build_upstream,
            retry_delays=(),
        )
        session = MCPGatewaySession(
            session_id=f"s{len(sessions)}",
            resource_service=resources,
            supervisor=supervisor,
            discovery=CapabilityDiscovery(
                resource_service=resources, supervisor=supervisor, preferences=prefs
            ),
            preferences=prefs,
            invocations=invocations,
        )
        sessions.append(session)
        await session.handle_initialize(
            {
                "protocolVersion": "2025-06-18",
                "capabilities": caps,
                "clientInfo": {"name": "test", "version": "1"},
            }
        )
        return _Client(session, answer, root)

    async def register(name: str, transport: dict[str, Any]) -> None:
        await resources.register(
            kind="mcp_server", name=name, config={"transport": transport}, actor="test"
        )

    yield register, client
    for session in sessions:
        with suppress(Exception):
            await session.dispose()
    with suppress(asyncio.CancelledError, Exception):
        await engine.dispose()


def _stdio() -> dict[str, Any]:
    return {"type": "stdio", "command": sys.executable, "args": [str(_FIXTURE)]}


@pytest.mark.parametrize("transport", ["stdio", "http"])
@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="two clients each answer their own upstream's sampling and roots"
)
async def test_each_client_answers_its_own_sampling_and_roots(
    gateway: Any, http_upstream: str, transport: str
) -> None:
    register, client = gateway
    await register(
        "asker", _stdio() if transport == "stdio" else {"type": "http", "url": http_upstream}
    )
    a = await client(_BOTH, answer="from-a", root="file:///a")
    b = await client(_BOTH, answer="from-b", root="file:///b")

    results = await asyncio.gather(
        a.call("asker__sample"),
        b.call("asker__sample"),
        a.call("asker__roots"),
        b.call("asker__roots"),
    )

    assert results == [
        ("sampled:from-a", False),
        ("sampled:from-b", False),
        ("roots:file:///a", False),
        ("roots:file:///b", False),
    ]
    assert sorted(a.asked) == sorted(b.asked) == ["roots/list", "sampling/createMessage"]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a client that declared no sampling is never asked to sample"
)
async def test_a_client_without_the_capability_is_never_asked(gateway: Any) -> None:
    register, client = gateway
    await register("asker", _stdio())
    plain = await client({})

    sample, sample_refused = await plain.call("asker__sample")
    roots, roots_refused = await plain.call("asker__roots")

    assert sample_refused and sample.startswith("refused:")
    assert roots_refused and roots.startswith("refused:")
    assert plain.asked == []
