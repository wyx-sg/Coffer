"""Integration tests for the /mcp endpoint."""

from __future__ import annotations

import sys
from contextlib import suppress
from pathlib import Path

import keyring
import keyring.core
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
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
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import set_mcp_session_factory
from coffer.surfaces.http.mcp.protocol_routes import (
    _ACTIVE_SESSIONS,
    _JSON_RPC_INTERNAL_ERROR,
    _JSON_RPC_METHOD_NOT_FOUND,
    _LAST_ACTIVITY,
    _NOTIFICATION_QUEUES,
    _QUEUE_MAXSIZE,
    reap_idle_sessions,
    shutdown_all_sessions,
)
from coffer.surfaces.http.mcp.protocol_routes import (
    router as mcp_router,
)

_FAKE = Path(__file__).resolve().parents[4] / "fixtures" / "fake_mcp_server.py"


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1.0  # type: ignore[assignment]

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get_password(self, s: str, u: str) -> str | None:
        return self._data.get((s, u))

    def set_password(self, s: str, u: str, p: str) -> None:
        self._data[(s, u)] = p

    def delete_password(self, s: str, u: str) -> None:
        self._data.pop((s, u), None)


def _with_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keyring.core, "_keyring_backend", _InMemoryKeyring())


def _stdio_config(*tools: str) -> dict:  # type: ignore[type-arg]
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", "--tools", *tools],
        },
    }


async def _build_app(
    tmp_path: Path,
) -> tuple[FastAPI, object]:  # returns (app, engine)
    """Wire up services and return a configured FastAPI app + engine for cleanup."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    rsvc = ResourceService(
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

    await rsvc.register(
        kind="mcp_server",
        name="fs",
        config=_stdio_config("read_file", "write_file"),
        actor="test",
    )

    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    inv_repo = MCPInvocationRepo(sm)

    def factory(session_id: str) -> MCPGatewaySession:
        supervisor = SubprocessSupervisor(
            resource_service=rsvc,
            credential_resolver=CredentialResolver(KeyringAdapter()),
        )
        discovery = CapabilityDiscovery(
            resource_service=rsvc,
            supervisor=supervisor,
            preferences=prefs_repo,
            audit=audit,
        )
        return MCPGatewaySession(
            session_id=session_id,
            resource_service=rsvc,
            supervisor=supervisor,
            discovery=discovery,
            preferences=prefs_repo,
            invocations=inv_repo,
        )

    set_mcp_session_factory(factory)
    set_active_token("test-token")

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(mcp_router)

    return app, engine


@pytest.fixture
async def http_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Async fixture: builds the app and yields an httpx.AsyncClient."""
    _with_in_memory(monkeypatch)
    # Clear module-level state from previous tests
    _ACTIVE_SESSIONS.clear()
    _NOTIFICATION_QUEUES.clear()
    _LAST_ACTIVITY.clear()

    app, engine = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Coffer-Token": "test-token"},
    ) as client:
        yield client

    await shutdown_all_sessions()
    with suppress(BaseException):
        await engine.dispose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_post_initialize_returns_capabilities(
    http_client: AsyncClient,
) -> None:
    r = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["serverInfo"]["name"] == "coffer"
    assert "mcp-session-id" in r.headers


@pytest.mark.asyncio
async def test_post_initialize_then_tools_list_in_same_session(
    http_client: AsyncClient,
) -> None:
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    session_id = init.headers["mcp-session-id"]

    r = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={"Mcp-Session-Id": session_id},
    )
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {"fs__read_file", "fs__write_file"}


@pytest.mark.asyncio
async def test_post_without_token_returns_401(
    http_client: AsyncClient,
) -> None:
    r = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"X-Coffer-Token": "wrong"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_post_unknown_method_returns_json_rpc_error(
    http_client: AsyncClient,
) -> None:
    r = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "nonexistent/method"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] in (_JSON_RPC_METHOD_NOT_FOUND, _JSON_RPC_INTERNAL_ERROR)


@pytest.mark.asyncio
async def test_post_tools_call_routes_through_gateway(
    http_client: AsyncClient,
) -> None:
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    session_id = init.headers["mcp-session-id"]
    # Discovery first so preferences populate
    await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers={"Mcp-Session-Id": session_id},
    )
    r = await http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "fs__read_file", "arguments": {"path": "/tmp/x"}},
        },
        headers={"Mcp-Session-Id": session_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert "result" in body
    assert "content" in body["result"]


@pytest.mark.asyncio
async def test_post_tools_call_with_payload_over_64kib_round_trips(
    http_client: AsyncClient,
) -> None:
    """A tools/call whose arguments exceed 64 KiB must round-trip through the
    daemon → upstream stdio write without breaking the connection.

    Guards against a second size ceiling beyond the shim fix: the daemon writes
    the request to the upstream's stdin and the upstream reads it back. Neither
    leg may impose a ~64 KiB line cap.
    """
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    session_id = init.headers["mcp-session-id"]
    await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers={"Mcp-Session-Id": session_id},
    )
    big_arg = "y" * (256 * 1024)  # 256 KiB, well past the 64 KiB ceiling
    r = await http_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "fs__read_file", "arguments": {"path": big_arg}},
        },
        headers={"Mcp-Session-Id": session_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "result" in body, body
    # The fake upstream echoes its arguments back — confirms the full >64 KiB
    # payload reached the upstream intact, not just that the call didn't error.
    assert big_arg in r.text


@pytest.mark.asyncio
async def test_post_malformed_json_returns_400(
    http_client: AsyncClient,
) -> None:
    r = await http_client.post(
        "/mcp",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_without_session_id_400(
    http_client: AsyncClient,
) -> None:
    r = await http_client.get("/mcp")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_with_session_id_accepted(
    http_client: AsyncClient,
) -> None:
    """GET /mcp with a valid session id opens an SSE stream; without a session
    id it is rejected with 400.

    httpx's ASGITransport buffers the whole response body, so the never-ending
    SSE stream can't be exercised through the client. We instead call the route
    handler directly and assert it returns an EventSourceResponse (the SSE
    content type) — without ever iterating the generator — which is the real
    "GET with session id is accepted as a stream" contract.
    """
    from sse_starlette.sse import EventSourceResponse

    from coffer.surfaces.http.dependencies import get_mcp_session_factory
    from coffer.surfaces.http.mcp.protocol_routes import handle_get

    # Valid POST initialize → session registered
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert init.status_code == 200
    session_id = init.headers["mcp-session-id"]
    assert session_id in _ACTIVE_SESSIONS

    # GET WITH a valid session id → an SSE EventSourceResponse (constructing it
    # does NOT start the generator, so this does not block).
    factory = get_mcp_session_factory()
    resp = await handle_get(mcp_session_id=session_id, factory=factory)
    assert isinstance(resp, EventSourceResponse)
    assert resp.media_type == "text/event-stream"

    # GET without session id → 400.
    r = await http_client.get("/mcp")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_sse_queue_is_bounded_and_drops_oldest(
    http_client: AsyncClient,
) -> None:
    """A noisy upstream pushing notifications faster than the downstream client
    drains them must NOT grow memory unbounded. The bounded queue drops the
    oldest message when full so the latest server view is always retained."""
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    session_id = init.headers["mcp-session-id"]
    session = _ACTIVE_SESSIONS[session_id]

    queue = _NOTIFICATION_QUEUES[session_id]
    assert queue.maxsize == _QUEUE_MAXSIZE

    # Push 5 more notifications than the queue can hold; verify the queue
    # never exceeds its maxsize and the *latest* messages survive.
    sink = session._downstream_sink
    assert sink is not None
    for i in range(_QUEUE_MAXSIZE + 5):
        await sink({"method": "notifications/test", "params": {"seq": i}})

    assert queue.qsize() == _QUEUE_MAXSIZE
    # Drain and confirm the survivors are the last _QUEUE_MAXSIZE messages.
    survivors = []
    while not queue.empty():
        survivors.append(queue.get_nowait())
    assert len(survivors) == _QUEUE_MAXSIZE
    # The earliest survivor must carry seq=5 (seqs 0..4 were dropped).
    import json

    first_seq = json.loads(survivors[0])["params"]["seq"]
    assert first_seq == 5


@pytest.mark.asyncio
async def test_reap_idle_sessions_drops_stale_only(
    http_client: AsyncClient,
) -> None:
    """The reaper must drop sessions whose last_activity is older than the
    threshold, and leave fresh ones alone."""
    # Create two sessions
    init_a = await http_client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    )
    session_a = init_a.headers["mcp-session-id"]
    init_b = await http_client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    )
    session_b = init_b.headers["mcp-session-id"]

    assert session_a in _ACTIVE_SESSIONS
    assert session_b in _ACTIVE_SESSIONS

    # Backdate session_a's last_activity to look stale.
    _LAST_ACTIVITY[session_a] = _LAST_ACTIVITY[session_a] - 10_000

    reaped = await reap_idle_sessions(max_idle_seconds=3600)
    assert session_a in reaped
    assert session_b not in reaped
    assert session_a not in _ACTIVE_SESSIONS
    assert session_b in _ACTIVE_SESSIONS


# ---------------------------------------------------------------------------
# T4 — downstream notifications/initialized and ping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downstream_initialized_notification_is_accepted(
    http_client: AsyncClient,
) -> None:
    """POST notifications/initialized (no id) must return 200 with empty body."""
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    session_id = init.headers["mcp-session-id"]

    r = await http_client.post(
        "/mcp",
        # notifications have no "id" field
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Mcp-Session-Id": session_id},
    )
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_downstream_ping_returns_empty_result(
    http_client: AsyncClient,
) -> None:
    """POST ping must return JSON-RPC result: {} (empty object)."""
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    session_id = init.headers["mcp-session-id"]

    r = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
        headers={"Mcp-Session-Id": session_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert "result" in body
    assert body["result"] == {}


@pytest.mark.asyncio
async def test_downstream_ping_notification_no_id_returns_202(
    http_client: AsyncClient,
) -> None:
    """A ping sent as a notification (no 'id') must return 202 with no JSON-RPC body.

    JSON-RPC notifications are fire-and-forget: the server must never respond
    with a JSON-RPC response object, including for 'ping' which does not carry
    the 'notifications/' prefix.
    """
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    session_id = init.headers["mcp-session-id"]

    r = await http_client.post(
        "/mcp",
        # No "id" field → this is a notification, not a request
        json={"jsonrpc": "2.0", "method": "ping"},
        headers={"Mcp-Session-Id": session_id},
    )
    assert r.status_code == 202
    # Must not return a JSON-RPC response body
    assert r.content == b""


# ---------------------------------------------------------------------------
# T19 — server-initiated request response routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downstream_response_routes_to_pending_server_request(
    http_client: AsyncClient,
) -> None:
    """An envelope with 'id' and no 'method' is a downstream response to a
    server-initiated request.  handle_post must route it to
    handle_response_from_downstream and ACK with an empty 202 body (CODE-029:
    never a JSON `""` body, which the shim would forward as a stray wire line).

    We seed a pending Future in the session's ServerRequestRegistry, then POST
    the matching response envelope.  The Future must be resolved with the result.
    """
    import asyncio

    # Establish a session
    init = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    session_id = init.headers["mcp-session-id"]
    session = _ACTIVE_SESSIONS[session_id]

    # Seed a pending server-initiated request (id=42) directly in the registry.
    # CODE-031: pending requests are keyed by the STRING form of the id.
    loop = asyncio.get_event_loop()
    pending_future: asyncio.Future[object] = loop.create_future()
    registry = session._server_request_registry
    registry._pending["42"] = pending_future

    # POST a downstream response envelope (has 'id', no 'method')
    r = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 42, "result": {"value": "ok"}},
        headers={"Mcp-Session-Id": session_id},
    )
    # CODE-029: matched-response ack is an empty 202, not a JSON body.
    assert r.status_code == 202, r.text
    assert r.content == b"", f"ack must have an empty body, got {r.content!r}"

    # The pending future must now be resolved with the result payload
    assert pending_future.done(), "pending future was not resolved by the response"
    assert pending_future.result() == {"value": "ok"}
