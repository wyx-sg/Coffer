"""Integration tests for MCPGatewaySession."""

from __future__ import annotations

import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import keyring
import keyring.core
import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceNotFound, ToolDisabled
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, ResourceRef
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

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


async def _safe_dispose(engine: object) -> None:
    """engine.dispose() may raise CancelledError from anyio cancel scopes on
    Python 3.14 when subprocess connections are still GC-ing; suppress only
    the expected leakage (CancelledError + regular Exception).  Narrowed from
    BaseException so KeyboardInterrupt / SystemExit still propagate (TEST-004).
    """
    import asyncio as _asyncio

    with suppress(_asyncio.CancelledError, Exception):
        await engine.dispose()  # type: ignore[union-attr]


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


def _stdio_config(
    *,
    tools: list[str] | None = None,
    resources: list[str] | None = None,
    prompts: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    args = [str(_FAKE), "--scenario", "basic"]
    if tools is not None:
        args += ["--tools", *tools]
    if resources is not None:
        args += ["--resources", *resources]
    if prompts is not None:
        args += ["--prompts", *prompts]
    return {"transport": {"type": "stdio", "command": sys.executable, "args": args}}


async def _setup(
    tmp_path: Path,
    server_configs: dict[str, dict],  # type: ignore[type-arg]
    *,
    supervisor_retry_delays: tuple[float, ...] | None = None,
) -> tuple[
    MCPGatewaySession,
    ResourceService,
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    object,  # engine
]:
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

    sup_kwargs: dict = {
        "resource_service": resource_svc,
        "credential_resolver": CredentialResolver(KeyringAdapter()),
    }
    if supervisor_retry_delays is not None:
        sup_kwargs["retry_delays"] = supervisor_retry_delays
    supervisor = SubprocessSupervisor(**sup_kwargs)
    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    inv_repo = MCPInvocationRepo(sm)
    discovery = CapabilityDiscovery(
        resource_service=resource_svc,
        supervisor=supervisor,
        preferences=prefs_repo,
        audit=audit,
    )
    session = MCPGatewaySession(
        session_id="test-session",
        resource_service=resource_svc,
        supervisor=supervisor,
        discovery=discovery,
        preferences=prefs_repo,
        invocations=inv_repo,
    )
    return session, resource_svc, prefs_repo, inv_repo, engine


@pytest.mark.asyncio
async def test_initialize_returns_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(tmp_path, {})
    try:
        result = await session.handle_initialize({"protocolVersion": "2025-06-18"})
        assert result["serverInfo"]["name"] == "coffer"
        caps = result["capabilities"]
        assert "tools" in caps
        assert "resources" in caps
        assert "prompts" in caps
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="aggregate tools across servers in one client"
)
@pytest.mark.asyncio
async def test_tools_list_aggregates_two_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path,
        {
            "fs": _stdio_config(tools=["read_file", "write_file"]),
            "gh": _stdio_config(tools=["create_issue"]),
        },
    )
    try:
        result = await session.handle_request("tools/list")
        names = {t["name"] for t in result["tools"]}
        assert names == {"fs__read_file", "fs__write_file", "gh__create_issue"}
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="tool-name collision across servers is prevented"
)
@pytest.mark.asyncio
async def test_same_upstream_tool_name_namespaced_per_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two servers both expose `search`; the gateway prefixes each with the
    server name, so the client sees `srv_a__search` and `srv_b__search` as
    distinct entries and never the bare `search`."""
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path,
        {
            "srv_a": _stdio_config(tools=["search"]),
            "srv_b": _stdio_config(tools=["search"]),
        },
    )
    try:
        result = await session.handle_request("tools/list")
        names = {t["name"] for t in result["tools"]}
        assert "srv_a__search" in names
        assert "srv_b__search" in names
        # Bare upstream name must NEVER surface — that would collide.
        assert "search" not in names
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="route a tool call to the correct upstream"
)
@pytest.mark.asyncio
async def test_tools_call_routes_and_records_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, inv_repo, engine = await _setup(
        tmp_path, {"fs": _stdio_config(tools=["read_file"])}
    )
    try:
        # First trigger discovery so preferences are populated
        await session.handle_request("tools/list")
        result = await session.handle_request(
            "tools/call",
            {"name": "fs__read_file", "arguments": {"path": "/tmp/x.txt"}},
        )
        # The fake server echoes its call args
        assert isinstance(result, dict)
        assert "content" in result
        # One invocation row recorded
        invocations = await inv_repo.query(resource_name="fs")
        assert len(invocations) == 1
        assert invocations[0].status == "ok"
        assert invocations[0].capability_key == "read_file"
        assert invocations[0].session_id == "test-session"
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_tools_call_disabled_rejected_with_denied_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    session, rsvc, prefs_repo, inv_repo, engine = await _setup(
        tmp_path, {"fs": _stdio_config(tools=["read_file", "write_file"])}
    )
    try:
        # Trigger discovery to populate preferences
        await session.handle_request("tools/list")
        # Disable write_file
        resource = await rsvc.get(ResourceRef("mcp_server", "fs"))
        await prefs_repo.set_enabled(resource.id, "tool", "write_file", False)
        # Attempted call should raise + record denied
        with pytest.raises(ToolDisabled):
            await session.handle_request(
                "tools/call",
                {"name": "fs__write_file", "arguments": {}},
            )
        invocations = await inv_repo.query(resource_name="fs", status="denied")
        assert len(invocations) == 1
        assert invocations[0].capability_key == "write_file"
        assert invocations[0].duration_ms == 0
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_tools_call_unknown_server_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(tmp_path, {})
    try:
        with pytest.raises((ResourceNotFound, ToolDisabled)):
            await session.handle_request(
                "tools/call",
                {"name": "ghost__some_tool", "arguments": {}},
            )
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_tools_call_malformed_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(tmp_path, {})
    try:
        with pytest.raises(ToolDisabled):
            await session.handle_request(
                "tools/call",
                {"name": "no_prefix_here", "arguments": {}},
            )
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_resources_list_aggregates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path,
        {
            "fs": _stdio_config(tools=["stub"], resources=["file:///tmp/a.txt"]),
        },
    )
    try:
        result = await session.handle_request("resources/list")
        uris = [r["uri"] for r in result["resources"]]
        assert "coffer://fs/file:///tmp/a.txt" in uris
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="resources forward through the gateway")
@pytest.mark.asyncio
async def test_resources_read_routes_and_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, inv_repo, engine = await _setup(
        tmp_path,
        {"fs": _stdio_config(tools=["stub"], resources=["file:///tmp/a.txt"])},
    )
    try:
        # Trigger discovery to populate prefs
        await session.handle_request("resources/list")
        result = await session.handle_request(
            "resources/read",
            {"uri": "coffer://fs/file:///tmp/a.txt"},
        )
        assert isinstance(result, dict)
        assert "contents" in result
        invocations = await inv_repo.query(resource_name="fs")
        assert len(invocations) == 1
        assert invocations[0].status == "ok"
        assert invocations[0].capability_type == "resource"
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="prompts forward through the gateway")
@pytest.mark.asyncio
async def test_prompts_list_and_get(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path,
        {"gh": _stdio_config(tools=["stub"], prompts=["summarise"])},
    )
    try:
        list_result = await session.handle_request("prompts/list")
        prompt_names = {p["name"] for p in list_result["prompts"]}
        assert "gh__summarise" in prompt_names
        get_result = await session.handle_request(
            "prompts/get", {"name": "gh__summarise", "arguments": {}}
        )
        assert "messages" in get_result
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_notification_forwarding_invalidates_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When we feed a synthetic notification into _on_upstream_notification,
    the discovery cache is invalidated AND the notification is forwarded."""
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path, {"fs": _stdio_config(tools=["read_file"])}
    )
    forwarded: list[dict] = []  # type: ignore[type-arg]

    async def sink(payload: dict) -> None:  # type: ignore[type-arg]
        forwarded.append(payload)

    session.set_downstream_sink(sink)
    try:
        # Populate the cache
        await session.handle_request("tools/list")
        # Send a synthetic list_changed
        await session._on_upstream_notification(
            "fs",
            {"method": "notifications/tools/list_changed", "params": {}},
        )
        # Notification was forwarded
        assert any(n.get("method") == "notifications/tools/list_changed" for n in forwarded)
        # And the cache slice was invalidated — verify by checking the
        # internal cache state (treat as private — fragile but useful here)
        cache = session._discovery._caches.get("fs")
        assert cache is None or cache.tools is None
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_resources_updated_rewrites_uri(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(tmp_path, {})
    forwarded: list[dict] = []  # type: ignore[type-arg]

    async def sink(payload: dict) -> None:  # type: ignore[type-arg]
        forwarded.append(payload)

    session.set_downstream_sink(sink)
    try:
        await session._on_upstream_notification(
            "fs",
            {
                "method": "notifications/resources/updated",
                "params": {"uri": "file:///tmp/x.txt"},
            },
        )
        assert forwarded[0]["method"] == "notifications/resources/updated"
        assert forwarded[0]["params"]["uri"] == "coffer://fs/file:///tmp/x.txt"
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_aggregate_list_drops_dead_server_keeps_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tools/list with one healthy server and one unreachable server returns
    the healthy server's tools and silently omits the dead one.
    """
    _with_in_memory(monkeypatch)

    # Unreachable server: command that doesn't exist → spawn fails immediately.
    dead_config = {
        "transport": {
            "type": "stdio",
            "command": "/nonexistent/binary/does/not/exist",
            "args": [],
        },
        # Minimal retries so the test finishes quickly.
        "spawn_timeout_seconds": 5,
    }

    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path,
        {
            "live": _stdio_config(tools=["read_file"]),
            "dead": dead_config,
        },
    )
    try:
        import time

        start = time.monotonic()
        result = await session.handle_request("tools/list")
        elapsed = time.monotonic() - start

        names = {t["name"] for t in result["tools"]}

        # The live server's tool must appear.
        assert "live__read_file" in names, f"Expected live__read_file, got: {names}"

        # The dead server's tools must NOT appear.
        dead_tools = {n for n in names if n.startswith("dead__")}
        assert not dead_tools, f"Dead server tools appeared: {dead_tools}"

        # The whole list must complete within PER_SERVER_LIST_TIMEOUT + 2 s headroom.
        # The 2.0 s buffer covers asyncio scheduling jitter + subprocess teardown time.
        from coffer.application.mcp.gateway_aggregate_lists import PER_SERVER_LIST_TIMEOUT

        assert elapsed < PER_SERVER_LIST_TIMEOUT + 2.0, (
            f"tools/list took {elapsed:.1f}s — exceeded per-server budget"
        )
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="concurrent clients")
@pytest.mark.asyncio
async def test_concurrent_sessions_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two MCPGatewaySession instances against the same upstreams run concurrently
    via asyncio.gather — both get correct tool lists and tool call results, and
    neither blocks or interferes with the other.
    """
    import asyncio as _asyncio

    _with_in_memory(monkeypatch)

    configs = {
        "fs": _stdio_config(tools=["read_file", "write_file"]),
        "gh": _stdio_config(tools=["create_issue"]),
    }

    # Create two independent sessions (each with its own supervisor, per ADR-005).
    path_a = tmp_path / "a"
    path_b = tmp_path / "b"
    path_a.mkdir()
    path_b.mkdir()
    session_a, _rsvc_a, _prefs_a, _inv_a, engine_a = await _setup(path_a, configs)
    session_b, _rsvc_b, _prefs_b, _inv_b, engine_b = await _setup(path_b, configs)

    try:
        # Run both tool-list requests concurrently.
        result_a, result_b = await _asyncio.gather(
            session_a.handle_request("tools/list"),
            session_b.handle_request("tools/list"),
        )

        names_a = {t["name"] for t in result_a["tools"]}
        names_b = {t["name"] for t in result_b["tools"]}
        expected = {"fs__read_file", "fs__write_file", "gh__create_issue"}

        assert names_a == expected, f"Session A got wrong tools: {names_a}"
        assert names_b == expected, f"Session B got wrong tools: {names_b}"

        # Run both tool-call requests concurrently — each session routes to its own
        # upstream; results must be correct and must not bleed across sessions.
        call_a, call_b = await _asyncio.gather(
            session_a.handle_request(
                "tools/call",
                {"name": "fs__read_file", "arguments": {"path": "/tmp/a.txt"}},
            ),
            session_b.handle_request(
                "tools/call",
                {"name": "gh__create_issue", "arguments": {"title": "test"}},
            ),
        )

        # The fake server echoes its call args; both must produce valid responses.
        assert isinstance(call_a, dict), f"Session A tool call returned: {call_a!r}"
        assert "content" in call_a, f"Session A missing 'content' key: {call_a!r}"
        assert isinstance(call_b, dict), f"Session B tool call returned: {call_b!r}"
        assert "content" in call_b, f"Session B missing 'content' key: {call_b!r}"
    finally:
        await session_a.dispose()
        await session_b.dispose()
        await _safe_dispose(engine_a)
        await _safe_dispose(engine_b)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="upstream crash recovery")
@pytest.mark.asyncio
async def test_upstream_crash_mid_call_then_respawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upstream crash during a call surfaces a domain error, records a non-ok
    invocation, and the supervisor respawns on the next call so it succeeds.
    """
    _with_in_memory(monkeypatch)

    crash_args = [
        str(_FAKE),
        "--scenario",
        "crash",
        "--tools",
        "boom",
        "--crash-after-calls",
        "2",
    ]
    crash_config = {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": crash_args,
        }
    }
    # spawn_timeout_seconds=5 keeps retries snappy in tests
    crash_config["spawn_timeout_seconds"] = 5

    # Use retry_delays=() so respawn after crash is immediate — avoids the
    # default production delays (1 s, 5 s, 30 s) that can sleep ~36 s on CI.
    session, _rsvc, _prefs, inv_repo, engine = await _setup(
        tmp_path,
        {"crash_srv": crash_config},
        supervisor_retry_delays=(),
    )
    try:
        # Populate discovery cache so the first call resolves.
        await session.handle_request("tools/list")

        # --- First call: succeeds (configured to crash on its 2nd call) ---
        result1 = await session.handle_request(
            "tools/call", {"name": "crash_srv__boom", "arguments": {}}
        )
        assert isinstance(result1, dict)

        # --- Second call: upstream has exited after the 1st call → error ---
        # The crash surfaces as McpError("Connection closed") or UpstreamUnavailable
        # depending on how quickly the SDK detects the dead pipe.
        with pytest.raises(BaseException):  # noqa: B017
            await session.handle_request("tools/call", {"name": "crash_srv__boom", "arguments": {}})

        # The invocation log must have an "error" row for the crash and at
        # least one "ok" row for the successful first call.  Using "error" (not
        # just "!= ok") ensures a stray "denied" row from an unrelated subtest
        # cannot falsely satisfy the assertion.
        invocations = await inv_repo.query(resource_name="crash_srv")
        statuses = [i.status for i in invocations]
        assert "error" in statuses, (
            f"Expected an 'error' invocation row for the crash call, got: {statuses}"
        )
        assert statuses.count("ok") >= 1, (
            f"Expected at least one 'ok' invocation row for the first call, got: {statuses}"
        )

        # --- Third call: supervisor respawns and succeeds ---
        result3 = await session.handle_request(
            "tools/call", {"name": "crash_srv__boom", "arguments": {}}
        )
        assert isinstance(result3, dict)
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="upstream tool list changes mid-session")
@pytest.mark.asyncio
async def test_upstream_list_change_forwarded_to_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real mutating upstream fires list_changed; the gateway forwards it downstream
    and the subsequent tools/list reflects the mutated (shrunk) tool set.
    """
    _with_in_memory(monkeypatch)

    # Build a mutating config: tools=[a, b], notify after 1st call.
    # After the notification fires, list_tools() drops the first tool ("a").
    mutating_args = [
        str(_FAKE),
        "--scenario",
        "mutating",
        "--tools",
        "a",
        "b",
        "--notify-list-changed-after",
        "1",
    ]
    mutating_config = {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": mutating_args,
        }
    }
    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path,
        {"mut": mutating_config},
    )
    forwarded: list[dict] = []  # type: ignore[type-arg]

    async def sink(payload: dict) -> None:  # type: ignore[type-arg]
        forwarded.append(payload)

    session.set_downstream_sink(sink)
    try:
        # Populate the cache and subscribe to notifications.
        initial = await session.handle_request("tools/list")
        initial_names = {t["name"] for t in initial["tools"]}
        assert initial_names == {"mut__a", "mut__b"}

        # Trigger the upstream tool call that fires send_tool_list_changed().
        await session.handle_request("tools/call", {"name": "mut__a", "arguments": {}})

        # Poll until the notification arrives (or 3 s timeout).
        # A fixed sleep is fragile: too short on slow CI, wasteful on fast machines.
        import asyncio as _asyncio

        async def _wait_for_list_changed() -> None:
            while not any(n.get("method") == "notifications/tools/list_changed" for n in forwarded):
                await _asyncio.sleep(0.05)

        await _asyncio.wait_for(_wait_for_list_changed(), timeout=3.0)

        # (a) The downstream sink received a list_changed notification.
        assert any(n.get("method") == "notifications/tools/list_changed" for n in forwarded), (
            f"No list_changed in forwarded notifications: {forwarded}"
        )

        # (b) A subsequent tools/list reflects the mutated (shrunk) set.
        # The gateway invalidated its cache on the notification, so it re-queries.
        updated = await session.handle_request("tools/list")
        updated_names = {t["name"] for t in updated["tools"]}
        # After list_changed_fired, the fake server drops tool "a".
        assert updated_names == {"mut__b"}, f"Expected only mut__b, got {updated_names}"
    finally:
        await session.dispose()
        await _safe_dispose(engine)


@pytest.mark.asyncio
async def test_dispose_closes_supervisor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_in_memory(monkeypatch)
    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path, {"fs": _stdio_config(tools=["read_file"])}
    )
    await session.handle_request("tools/list")
    await session.dispose()
    # subsequent dispose is safe (idempotent)
    await session.dispose()
    assert session._notification_subscriptions == set()
    await _safe_dispose(engine)


# ---------------------------------------------------------------------------
# T23 — evict-on-crash parity: resources/read and prompts/get
# ---------------------------------------------------------------------------


class _SpySupervisor:
    """Minimal supervisor stub that returns a boom-connection and tracks evictions."""

    def __init__(self, boom_conn: object, evicted: list[str]) -> None:
        self._boom_conn = boom_conn
        self._evicted = evicted

    async def get_or_spawn(self, name: str) -> object:
        return self._boom_conn

    async def evict(self, name: str) -> None:
        self._evicted.append(name)


async def _build_crash_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    db_name: str,
    server_name: str,
    server_config: dict,  # type: ignore[type-arg]
) -> tuple[
    ResourceService,
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    _SpySupervisor,
    object,  # engine — caller must dispose
]:
    """Build the (rsvc, prefs, inv, spy_supervisor, engine) harness for T23 tests."""
    _with_in_memory(monkeypatch)

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / db_name}")
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
        name=server_name,
        config=server_config,
        actor="test",
    )
    prefs = MCPCapabilityPreferenceRepo(sm)
    inv = MCPInvocationRepo(sm)

    boom_conn = AsyncMock()
    boom_conn.request.side_effect = RuntimeError("pipe broken")
    evicted: list[str] = []
    spy_supervisor = _SpySupervisor(boom_conn, evicted)

    return rsvc, prefs, inv, spy_supervisor, engine


# ---------------------------------------------------------------------------
# TEST-020 — disabled (denied) + timeout invocation rows for resources/prompts
# ---------------------------------------------------------------------------


async def _build_simple_harness_with_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    db_name: str,
    server_name: str,
    transport: dict,  # type: ignore[type-arg]
    supervisor: object,
) -> tuple[
    ResourceService,
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    object,  # engine
]:
    """Mirror of _build_crash_harness but uses a caller-provided supervisor.

    Useful for TEST-020 where we want a supervisor whose `get_or_spawn`
    returns a connection that ALWAYS raises a chosen exception type
    (UpstreamTimeout, RuntimeError, …) so the timeout/error branches of the
    invocation handlers can be exercised deterministically.
    """
    _with_in_memory(monkeypatch)
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / db_name}")
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
        name=server_name,
        config={"transport": transport},
        actor="test",
    )
    prefs = MCPCapabilityPreferenceRepo(sm)
    inv = MCPInvocationRepo(sm)
    return rsvc, prefs, inv, engine


@pytest.mark.parametrize(
    ("handler_module_attr", "params_factory", "capability_type", "capability_key"),
    [
        (
            "handle_tools_call",
            lambda: {"name": "fs__read_file", "arguments": {}},
            "tool",
            "read_file",
        ),
        (
            "handle_resources_read",
            lambda: {"uri": "coffer://fs/file:///x"},
            "resource",
            "file:///x",
        ),
        (
            "handle_prompts_get",
            lambda: {"name": "fs__summarise"},
            "prompt",
            "summarise",
        ),
    ],
)
@pytest.mark.asyncio
async def test_handler_disabled_records_denied_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    handler_module_attr: str,
    params_factory: object,
    capability_type: str,
    capability_key: str,
) -> None:
    """TEST-020: tools/resources/prompts each record a `denied` invocation
    row when the requested capability is disabled in the preferences repo.
    """
    from coffer.application.mcp import gateway_handlers

    rsvc, prefs, inv, engine = await _build_simple_harness_with_supervisor(
        tmp_path,
        monkeypatch,
        db_name=f"den_{capability_type}.db",
        server_name="fs",
        transport={
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--tools", "stub"],
        },
        supervisor=None,
    )
    try:
        # Pre-seed prefs with capability disabled so check_capability_enabled
        # sees a row and short-circuits with ToolDisabled.  set_enabled is a
        # no-op when the row is absent, so we use insert() directly.
        resource = await rsvc.get(ResourceRef("mcp_server", "fs"))
        now = datetime.now(tz=UTC)
        await prefs.insert(
            resource_id=resource.id,
            capability_type=capability_type,  # type: ignore[arg-type]
            capability_key=capability_key,
            enabled=False,
            first_seen_at=now,
            last_seen_at=now,
        )

        async def _noop_subscribe(name: str) -> None:
            pass

        handler = getattr(gateway_handlers, handler_module_attr)

        with pytest.raises(ToolDisabled):
            await handler(
                params_factory(),  # type: ignore[operator]
                resources=rsvc,
                supervisor=AsyncMock(),
                prefs=prefs,
                invocations=inv,
                session_id="t",
                clock=lambda: datetime.now(tz=UTC),
                ensure_subscribed=_noop_subscribe,
            )

        rows = await inv.query(resource_name="fs")
        denied = [r for r in rows if r.status == "denied"]
        assert len(denied) == 1, f"expected exactly one denied invocation, got: {rows}"
        assert denied[0].capability_type == capability_type
        assert denied[0].capability_key == capability_key
        assert denied[0].duration_ms == 0
    finally:
        await _safe_dispose(engine)


@pytest.mark.parametrize(
    ("handler_module_attr", "params_factory", "capability_type", "capability_key"),
    [
        (
            "handle_tools_call",
            lambda: {"name": "fs__read_file", "arguments": {}},
            "tool",
            "read_file",
        ),
        (
            "handle_resources_read",
            lambda: {"uri": "coffer://fs/file:///x"},
            "resource",
            "file:///x",
        ),
        (
            "handle_prompts_get",
            lambda: {"name": "fs__summarise"},
            "prompt",
            "summarise",
        ),
    ],
)
@pytest.mark.asyncio
async def test_handler_records_timeout_invocation_on_upstream_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    handler_module_attr: str,
    params_factory: object,
    capability_type: str,
    capability_key: str,
) -> None:
    """TEST-020: tools/resources/prompts each record a `timeout` invocation
    row when the upstream raises UpstreamTimeout.
    """
    from coffer.application.mcp import gateway_handlers
    from coffer.domain.errors import UpstreamTimeout

    rsvc, prefs, inv, engine = await _build_simple_harness_with_supervisor(
        tmp_path,
        monkeypatch,
        db_name=f"to_{capability_type}.db",
        server_name="fs",
        transport={
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--tools", "stub"],
        },
        supervisor=None,
    )
    try:
        # Use a supervisor whose get_or_spawn returns a connection whose
        # request() raises UpstreamTimeout.  No real subprocess needed.
        boom_conn = AsyncMock()
        boom_conn.request.side_effect = UpstreamTimeout("simulated upstream timeout")
        evicted: list[str] = []

        class _SpySup:
            async def get_or_spawn(self, name: str) -> object:
                return boom_conn

            async def evict(self, name: str) -> None:
                evicted.append(name)

        async def _noop_subscribe(name: str) -> None:
            pass

        handler = getattr(gateway_handlers, handler_module_attr)

        with pytest.raises(UpstreamTimeout):
            await handler(
                params_factory(),  # type: ignore[operator]
                resources=rsvc,
                supervisor=_SpySup(),  # type: ignore[arg-type]
                prefs=prefs,
                invocations=inv,
                session_id="t",
                clock=lambda: datetime.now(tz=UTC),
                ensure_subscribed=_noop_subscribe,
            )

        rows = await inv.query(resource_name="fs")
        timed_out = [r for r in rows if r.status == "timeout"]
        assert len(timed_out) == 1, f"expected exactly one timeout invocation, got: {rows}"
        assert timed_out[0].capability_type == capability_type
        assert timed_out[0].capability_key == capability_key
        # Spec says the timeout branch does NOT evict the connection.
        assert evicted == []
    finally:
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="upstream crash recovery")
@pytest.mark.asyncio
async def test_upstream_crash_mid_resource_read_then_respawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An upstream exception during resources/read must call supervisor.evict()
    so the next call triggers a fresh spawn.
    """
    from coffer.application.mcp.gateway_handlers import handle_resources_read

    rsvc, prefs, inv, spy_supervisor, engine = await _build_crash_harness(
        tmp_path,
        monkeypatch,
        db_name="rr.db",
        server_name="fs",
        server_config={
            "transport": {
                "type": "stdio",
                "command": sys.executable,
                "args": [str(_FAKE), "--resources", "file:///x"],
            }
        },
    )

    async def _noop_subscribe(name: str) -> None:
        pass

    try:
        with pytest.raises(RuntimeError, match="pipe broken"):
            await handle_resources_read(
                {"uri": "coffer://fs/file:///x"},
                resources=rsvc,
                supervisor=spy_supervisor,  # type: ignore[arg-type]
                prefs=prefs,
                invocations=inv,
                session_id="t",
                clock=lambda: datetime.now(tz=UTC),
                ensure_subscribed=_noop_subscribe,
            )

        # supervisor.evict() must have been called with the server name.
        assert spy_supervisor._evicted == ["fs"], (
            f"evict not called; evicted={spy_supervisor._evicted}"
        )

        # An error invocation row must have been recorded.
        rows = await inv.query(resource_name="fs")
        assert any(r.status == "error" for r in rows), f"no error row; rows={rows}"
    finally:
        await _safe_dispose(engine)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="upstream crash recovery")
@pytest.mark.asyncio
async def test_upstream_crash_mid_prompt_get_then_respawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An upstream exception during prompts/get must call supervisor.evict()
    so the next call triggers a fresh spawn.
    """
    from coffer.application.mcp.gateway_handlers import handle_prompts_get

    rsvc, prefs, inv, spy_supervisor, engine = await _build_crash_harness(
        tmp_path,
        monkeypatch,
        db_name="pg.db",
        server_name="gh",
        server_config={
            "transport": {
                "type": "stdio",
                "command": sys.executable,
                "args": [str(_FAKE), "--prompts", "summarise"],
            }
        },
    )

    async def _noop_subscribe(name: str) -> None:
        pass

    try:
        with pytest.raises(RuntimeError, match="pipe broken"):
            await handle_prompts_get(
                {"name": "gh__summarise"},
                resources=rsvc,
                supervisor=spy_supervisor,  # type: ignore[arg-type]
                prefs=prefs,
                invocations=inv,
                session_id="t",
                clock=lambda: datetime.now(tz=UTC),
                ensure_subscribed=_noop_subscribe,
            )

        assert spy_supervisor._evicted == ["gh"], (
            f"evict not called; evicted={spy_supervisor._evicted}"
        )

        rows = await inv.query(resource_name="gh")
        assert any(r.status == "error" for r in rows), f"no error row; rows={rows}"
    finally:
        await _safe_dispose(engine)


# ---------------------------------------------------------------------------
# Fix 1 — re-subscribe to notifications after crash-evict
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="upstream tool list changes mid-session")
@pytest.mark.asyncio
async def test_notification_resubscribed_after_crash_evict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After an upstream crash + evict, the respawned connection must have its
    notification callback re-registered so list_changed notifications are not
    silently dropped.

    Scenario:
    - mutating server with crash-after-calls=2 and notify-list-changed-after=1.
    - Process 1: call#1 fires list_changed; call#2 crashes → evict.
    - Process 2 (respawn): call#3 fires list_changed again (notify_after=1 on
      the new process).  Without the fix, _notification_subscriptions still
      contains the server name so _ensure_subscribed short-circuits and the new
      connection never gets the callback → notification is dropped.  With the
      fix, the name is discarded from _notification_subscriptions on evict, so
      _ensure_subscribed re-registers the callback.
    """
    import asyncio as _asyncio

    _with_in_memory(monkeypatch)

    # mutating scenario: fires list_changed on the 1st call of each process.
    # crash-after-calls=2: the first process exits after its 2nd call.
    mutating_crash_args = [
        str(_FAKE),
        "--scenario",
        "mutating",
        "--tools",
        "x",
        "y",
        "--notify-list-changed-after",
        "1",
        "--crash-after-calls",
        "2",
    ]
    server_config = {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": mutating_crash_args,
        },
        "spawn_timeout_seconds": 5,
    }

    session, _rsvc, _prefs, _inv, engine = await _setup(
        tmp_path,
        {"mut": server_config},
        supervisor_retry_delays=(),
    )
    forwarded: list[dict] = []  # type: ignore[type-arg]

    async def sink(payload: dict) -> None:  # type: ignore[type-arg]
        forwarded.append(payload)

    session.set_downstream_sink(sink)
    try:
        # Populate discovery and subscribe.
        await session.handle_request("tools/list")

        # --- Call #1 on Process 1: succeeds + fires list_changed notification ---
        await session.handle_request("tools/call", {"name": "mut__x", "arguments": {}})

        async def _wait_for_list_changed(min_count: int) -> None:
            while (
                sum(1 for n in forwarded if n.get("method") == "notifications/tools/list_changed")
                < min_count
            ):
                await _asyncio.sleep(0.05)

        # Wait for the first notification from Process 1.
        await _asyncio.wait_for(_wait_for_list_changed(1), timeout=3.0)
        count_after_p1 = sum(
            1 for n in forwarded if n.get("method") == "notifications/tools/list_changed"
        )
        assert count_after_p1 >= 1, "Process 1 notification never arrived"

        # --- Call #2 on Process 1: crashes → supervisor.evict("mut") called ---
        with pytest.raises(BaseException):  # noqa: B017
            await session.handle_request("tools/call", {"name": "mut__x", "arguments": {}})

        # --- Call #3: supervisor respawns Process 2 immediately (retry_delays=()).
        #     Process 2's first call fires list_changed again (notify_after=1 resets
        #     per-process) and returns a normal result. ---
        # The call may succeed OR may still fail if the supervisor is mid-respawn;
        # either way, we ultimately just need the notification to arrive.
        with suppress(BaseException):
            await session.handle_request("tools/call", {"name": "mut__x", "arguments": {}})
        # If the first post-respawn call also failed (supervisor still racing),
        # make one more attempt so P2 has had at least one call to fire the notification.
        with suppress(BaseException):
            await session.handle_request("tools/call", {"name": "mut__x", "arguments": {}})

        # Poll for the second list_changed notification (from Process 2).
        # Without the fix this never arrives; with the fix it does.
        await _asyncio.wait_for(_wait_for_list_changed(count_after_p1 + 1), timeout=5.0)

        count_after_p2 = sum(
            1 for n in forwarded if n.get("method") == "notifications/tools/list_changed"
        )
        assert count_after_p2 >= count_after_p1 + 1, (
            f"Expected a list_changed notification from the respawned upstream "
            f"(Process 2), but only got {count_after_p2} total. "
            f"This means the new connection never had its notification callback "
            f"registered — the re-subscribe-after-evict fix is missing."
        )
    finally:
        await session.dispose()
        await _safe_dispose(engine)
