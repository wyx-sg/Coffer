"""Integration tests for MCP capability/refresh/test REST endpoints."""

from __future__ import annotations

import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, ResourceRef
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
    MCPServerHealthRepo,
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
from coffer.surfaces.http.dependencies import (
    get_audit_service,
    get_capability_discovery,
    get_credential_store,
    get_health_repo,
    get_invocation_repo,
    get_preferences_repo,
    get_resource_service,
)
from coffer.surfaces.http.mcp.capability_routes import router as capability_router
from tests.fixtures.keyring import install_in_memory_keyring

_FAKE = Path(__file__).resolve().parents[4] / "fixtures" / "fake_mcp_server.py"


def _with_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    install_in_memory_keyring(monkeypatch)


def _stdio_config(*tools: str) -> dict[str, Any]:
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", "--tools", *tools],
        },
    }


def _stdio_config_with_resources_prompts(
    tools: list[str],
    resources: list[str],
    prompts: list[str],
) -> dict[str, Any]:
    args = [str(_FAKE), "--scenario", "basic", "--tools", *tools]
    if resources:
        args += ["--resources", *resources]
    if prompts:
        args += ["--prompts", *prompts]
    return {"transport": {"type": "stdio", "command": sys.executable, "args": args}}


class _InMemoryCredentialStore:
    """Empty credential store — capability tests register servers without credential_refs."""

    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:  # pragma: no cover - unused
        pass

    def delete(self, ref: str) -> None:  # pragma: no cover - unused
        pass


async def _build_app(
    tmp_path: Path,
    *,
    tools: list[str] | None = None,
    resources: list[str] | None = None,
    prompts: list[str] | None = None,
    server_name: str = "fs",
) -> tuple[FastAPI, Any, ResourceService, MCPCapabilityPreferenceRepo, SubprocessSupervisor]:
    """Build a fully-wired FastAPI app for capability route tests."""
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

    _tools = tools if tools is not None else ["read_file", "write_file"]
    _resources = resources or []
    _prompts = prompts or []

    config = _stdio_config_with_resources_prompts(_tools, _resources, _prompts)
    await rsvc.register(kind="mcp_server", name=server_name, config=config, actor="test")

    prefs_repo = MCPCapabilityPreferenceRepo(sm)

    supervisor = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=rsvc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    discovery = CapabilityDiscovery(
        resource_service=rsvc,
        supervisor=supervisor,
        preferences=prefs_repo,
        audit=audit,
    )

    set_active_token("test-token")

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(capability_router)
    health_repo = MCPServerHealthRepo(sm)

    app.dependency_overrides[get_resource_service] = lambda: rsvc
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_capability_discovery] = lambda: discovery
    app.dependency_overrides[get_preferences_repo] = lambda: prefs_repo
    app.dependency_overrides[get_invocation_repo] = lambda: MCPInvocationRepo(sm)
    app.dependency_overrides[get_health_repo] = lambda: health_repo
    app.dependency_overrides[get_credential_store] = lambda: _InMemoryCredentialStore()

    return app, engine, rsvc, prefs_repo, supervisor


@pytest.fixture
async def client_and_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Yield (client, engine, rsvc, prefs_repo, supervisor)."""
    _with_in_memory(monkeypatch)
    app, engine, rsvc, prefs_repo, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Coffer-Token": "test-token"},
    ) as client:
        yield client, engine, rsvc, prefs_repo, supervisor

    await supervisor.dispose()
    with suppress(BaseException):
        await engine.dispose()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# List capabilities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_capabilities_returns_tools_resources_prompts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(
        tmp_path,
        tools=["read_file", "write_file"],
        resources=["file:///tmp/a.txt"],
        prompts=["summarise"],
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            r = await client.get("/api/v1/resources/mcp_server/fs/capabilities")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["server_name"] == "fs"
            tool_names = {t["prefixed_name"] for t in body["tools"]}
            assert tool_names == {"fs__read_file", "fs__write_file"}
            # enabled flag is present
            assert all(t["enabled"] is True for t in body["tools"])
            # resources
            resource_uris = {res["original_uri"] for res in body["resources"]}
            assert resource_uris == {"file:///tmp/a.txt"}
            # prompts
            prompt_names = {p["prefixed_name"] for p in body["prompts"]}
            assert prompt_names == {"fs__summarise"}
    finally:
        await supervisor.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_capabilities_tools_only_upstream_method_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tools-only upstream that replies -32601 METHOD_NOT_FOUND for
    resources/list and prompts/list must NOT fail the capability view.

    The fake server is launched with --no-resources --no-prompts so it does
    not register those handlers; the MCP SDK then replies with a genuine
    JSON-RPC -32601, exactly like a real tools-only upstream. The endpoint
    must return 200 with tools populated and resources == prompts == [],
    instead of the previous 500 INTERNAL_ERROR.
    """
    _with_in_memory(monkeypatch)

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
        name="toolsonly",
        config={
            "transport": {
                "type": "stdio",
                "command": sys.executable,
                "args": [
                    str(_FAKE),
                    "--scenario",
                    "basic",
                    "--tools",
                    "read_file",
                    "write_file",
                    "--no-resources",
                    "--no-prompts",
                ],
            }
        },
        actor="test",
    )

    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    supervisor = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=rsvc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    discovery = CapabilityDiscovery(
        resource_service=rsvc,
        supervisor=supervisor,
        preferences=prefs_repo,
        audit=audit,
    )

    set_active_token("test-token")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(capability_router)
    app.dependency_overrides[get_resource_service] = lambda: rsvc
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_capability_discovery] = lambda: discovery
    app.dependency_overrides[get_preferences_repo] = lambda: prefs_repo
    app.dependency_overrides[get_invocation_repo] = lambda: MCPInvocationRepo(sm)
    app.dependency_overrides[get_health_repo] = lambda: MCPServerHealthRepo(sm)
    app.dependency_overrides[get_credential_store] = lambda: _InMemoryCredentialStore()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            r = await client.get("/api/v1/resources/mcp_server/toolsonly/capabilities")
            assert r.status_code == 200, r.text
            body = r.json()
            tool_names = {t["prefixed_name"] for t in body["tools"]}
            assert tool_names == {"toolsonly__read_file", "toolsonly__write_file"}
            assert body["resources"] == []
            assert body["prompts"] == []
    finally:
        await supervisor.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_capabilities_returns_404_for_unknown_server(
    client_and_ctx: tuple,
) -> None:
    client, *_ = client_and_ctx
    r = await client.get("/api/v1/resources/mcp_server/nonexistent/capabilities")
    # An unregistered server makes get_or_spawn raise ResourceNotFound (NOT
    # UpstreamUnavailable), which the route does not catch → the global handler
    # maps it to a deterministic 404. Pin the exact code + error envelope so a
    # regression that swallowed it into a 503/500 would be caught.
    assert r.status_code == 404, r.text
    assert "error" in r.json()


@pytest.mark.asyncio
async def test_list_capabilities_times_out_on_hung_upstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CODE-M2: a dead/hung upstream must not let the management capabilities
    page hang for the supervisor's full retry ladder. The route applies a
    per-call timeout budget and surfaces 503 within it.
    """
    import asyncio

    from coffer.surfaces.http.mcp import capability_routes

    _with_in_memory(monkeypatch)
    # Shrink the budget so the test is fast but still proves the bound.
    monkeypatch.setattr(capability_routes, "_CAPABILITY_LIST_TIMEOUT", 0.1)

    class _HangingDiscovery:
        async def list_tools(self, name: str, include_disabled: bool = False) -> list:
            await asyncio.sleep(30)  # simulate a wedged upstream spawn
            return []

        async def list_resources(self, name: str, include_disabled: bool = False) -> list:
            await asyncio.sleep(30)
            return []

        async def list_prompts(self, name: str, include_disabled: bool = False) -> list:
            await asyncio.sleep(30)
            return []

    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    app.dependency_overrides[get_capability_discovery] = lambda: _HangingDiscovery()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            start = asyncio.get_event_loop().time()
            r = await client.get("/api/v1/resources/mcp_server/fs/capabilities")
            elapsed = asyncio.get_event_loop().time() - start
            assert r.status_code == 503, r.text
            assert elapsed < 5.0, f"route hung for {elapsed:.1f}s instead of failing fast"
    finally:
        await supervisor.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_capabilities_requires_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "wrong"},
        ) as client:
            r = await client.get("/api/v1/resources/mcp_server/fs/capabilities")
            assert r.status_code == 401
    finally:
        await supervisor.dispose()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Enable / disable capabilities
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="disable an individual capability")
@pytest.mark.asyncio
async def test_enable_disable_capability_flips_preference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            # First list to populate preferences
            r = await client.get("/api/v1/resources/mcp_server/fs/capabilities")
            assert r.status_code == 200

            # Disable write_file
            r = await client.post(
                "/api/v1/resources/mcp_server/fs/capabilities/tool/write_file/disable"
            )
            assert r.status_code == 204, r.text

            # List again — write_file is still present but marked disabled.
            # The management endpoint returns every capability with its
            # enabled flag so the UI can show and re-enable disabled ones;
            # only the gateway's client-facing list hides disabled tools.
            r = await client.get("/api/v1/resources/mcp_server/fs/capabilities")
            assert r.status_code == 200
            tools_by_name = {t["prefixed_name"]: t for t in r.json()["tools"]}
            assert tools_by_name["fs__write_file"]["enabled"] is False
            assert tools_by_name["fs__read_file"]["enabled"] is True

            # Re-enable write_file
            r = await client.post(
                "/api/v1/resources/mcp_server/fs/capabilities/tool/write_file/enable"
            )
            assert r.status_code == 204, r.text

            # Invalidate cache and re-list — write_file is enabled again
            r = await client.post("/api/v1/resources/mcp_server/fs/refresh")
            assert r.status_code == 200
            tools_by_name = {t["prefixed_name"]: t for t in r.json()["tools"]}
            assert tools_by_name["fs__write_file"]["enabled"] is True
    finally:
        await supervisor.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_enable_unknown_capability_returns_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            # Enable before discovery has ever run → preference row doesn't exist
            r = await client.post(
                "/api/v1/resources/mcp_server/fs/capabilities/tool/nonexistent_tool/enable"
            )
            assert r.status_code == 404
    finally:
        await supervisor.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_disable_unknown_capability_returns_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            r = await client.post(
                "/api/v1/resources/mcp_server/fs/capabilities/tool/ghost_tool/disable"
            )
            assert r.status_code == 404
    finally:
        await supervisor.dispose()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_invalidates_cache_and_returns_fresh_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            # Initial list
            r = await client.get("/api/v1/resources/mcp_server/fs/capabilities")
            assert r.status_code == 200
            assert len(r.json()["tools"]) == 2  # read_file + write_file

            # Disable one tool
            await client.post(
                "/api/v1/resources/mcp_server/fs/capabilities/tool/write_file/disable"
            )

            # Refresh: invalidates cache, re-queries, re-applies preferences.
            # Both tools come back; the disabled preference persists through
            # the refresh and surfaces as enabled=false (not filtered out).
            r = await client.post("/api/v1/resources/mcp_server/fs/refresh")
            assert r.status_code == 200
            tools_by_name = {t["prefixed_name"]: t for t in r.json()["tools"]}
            assert tools_by_name["fs__write_file"]["enabled"] is False
            assert tools_by_name["fs__read_file"]["enabled"] is True
    finally:
        await supervisor.dispose()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Test endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_endpoint_healthy_server_returns_ok(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            r = await client.post("/api/v1/resources/mcp_server/fs/test")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["latency_ms"] >= 0
            assert body["error_message"] is None
    finally:
        await supervisor.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_test_endpoint_unreachable_server_returns_ok_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
    # Register a server that points at a non-existent binary
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
        name="bad",
        config={
            "transport": {
                "type": "stdio",
                "command": "/nonexistent/binary/that/does/not/exist",
                "args": [],
            }
        },
        actor="test",
    )

    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    supervisor = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=rsvc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    discovery = CapabilityDiscovery(
        resource_service=rsvc,
        supervisor=supervisor,
        preferences=prefs_repo,
        audit=audit,
    )

    set_active_token("test-token")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(capability_router)
    app.dependency_overrides[get_resource_service] = lambda: rsvc
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_capability_discovery] = lambda: discovery
    app.dependency_overrides[get_preferences_repo] = lambda: prefs_repo
    app.dependency_overrides[get_invocation_repo] = lambda: MCPInvocationRepo(sm)
    app.dependency_overrides[get_health_repo] = lambda: MCPServerHealthRepo(sm)
    app.dependency_overrides[get_credential_store] = lambda: _InMemoryCredentialStore()

    transport_transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport_transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            r = await client.post("/api/v1/resources/mcp_server/bad/test")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is False
            assert body["error_message"] is not None
            assert len(body["error_message"]) > 0

            # T7: verify persisted health reflects the failure
            r_status = await client.get("/api/v1/resources/mcp_server/bad/status")
            assert r_status.status_code == 200, r_status.text
            assert r_status.json()["status"] == "failing", (
                f"Expected 'failing' after failed /test, got: {r_status.json()}"
            )
    finally:
        await supervisor.dispose()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Audit side-effects
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="audit lifecycle changes")
@pytest.mark.asyncio
async def test_enable_capability_creates_audit_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_in_memory(monkeypatch)
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
    config = _stdio_config("read_file", "write_file")
    await rsvc.register(kind="mcp_server", name="fs", config=config, actor="test")

    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    supervisor = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=rsvc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    discovery = CapabilityDiscovery(
        resource_service=rsvc,
        supervisor=supervisor,
        preferences=prefs_repo,
        audit=audit,
    )

    set_active_token("test-token")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(capability_router)
    app.dependency_overrides[get_resource_service] = lambda: rsvc
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_capability_discovery] = lambda: discovery
    app.dependency_overrides[get_preferences_repo] = lambda: prefs_repo
    app.dependency_overrides[get_invocation_repo] = lambda: MCPInvocationRepo(sm)
    app.dependency_overrides[get_health_repo] = lambda: MCPServerHealthRepo(sm)
    app.dependency_overrides[get_credential_store] = lambda: _InMemoryCredentialStore()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            # Populate prefs
            await client.get("/api/v1/resources/mcp_server/fs/capabilities")

            # Disable → audit event
            await client.post(
                "/api/v1/resources/mcp_server/fs/capabilities/tool/write_file/disable"
            )
            events = await audit.query(event_type="capability_disabled")
            assert len(events) == 1
            assert events[0].details["capability_key"] == "write_file"

            # Enable → audit event
            await client.post("/api/v1/resources/mcp_server/fs/capabilities/tool/write_file/enable")
            events = await audit.query(event_type="capability_enabled")
            assert len(events) == 1
            assert events[0].details["capability_key"] == "write_file"
    finally:
        await supervisor.dispose()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Server status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_status_unknown_then_healthy(client_and_ctx) -> None:
    """Status is `unknown` before discovery, `healthy` once capabilities
    have been persisted — derived from the DB, no upstream spawn."""
    client, _engine, rsvc, prefs_repo, _ = client_and_ctx

    r0 = await client.get("/api/v1/resources/mcp_server/fs/status")
    assert r0.status_code == 200
    assert r0.json()["status"] == "unknown"

    # Persisting a discovered capability flips the server to healthy.
    resource = await rsvc.get(ResourceRef("mcp_server", "fs"))
    now = datetime.now(tz=UTC)
    await prefs_repo.insert(resource.id, "tool", "read_file", True, now, now)

    r1 = await client.get("/api/v1/resources/mcp_server/fs/status")
    assert r1.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# T6 — /test passes server_name to StdioUpstreamConnection (orphan PID tracking)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_endpoint_records_orphan_pid_under_server_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /{name}/test must pass server_name to StdioUpstreamConnection so
    orphan PID files are keyed by server name, not the default 'upstream'."""
    import unittest.mock as mock

    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path, server_name="myserver")
    transport = ASGITransport(app=app)

    captured: list[str] = []

    # Must patch where the name is looked up (capability_routes local binding),
    # not where it is defined. We wrap the real class to intercept __init__.
    from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection as _RealConn

    class _CapturingConn(_RealConn):  # type: ignore[misc]
        def __init__(  # type: ignore[override]
            self,
            transport,
            env_overlay,
            spawn_timeout_seconds=30,
            request_timeout_seconds=120,
            server_name="upstream",
        ):
            captured.append(server_name)
            super().__init__(
                transport,
                env_overlay,
                spawn_timeout_seconds,
                request_timeout_seconds,
                server_name,
            )

    with mock.patch(
        "coffer.surfaces.http.mcp.capability_routes.StdioUpstreamConnection",
        _CapturingConn,
    ):
        try:
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
                headers={"X-Coffer-Token": "test-token"},
            ) as client:
                r = await client.post("/api/v1/resources/mcp_server/myserver/test")
                assert r.status_code == 200, r.text
        finally:
            await supervisor.dispose()
            await engine.dispose()

    assert captured, "StdioUpstreamConnection was not instantiated"
    assert captured[0] == "myserver", f"Expected server_name='myserver', got {captured[0]!r}"


# ---------------------------------------------------------------------------
# T7 — persisted upstream health state via mcp_server_health table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_endpoint_persists_health_and_status_reflects_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /{name}/test must write health result to mcp_server_health so that
    GET /{name}/status returns 'healthy' after a successful test (without
    relying solely on invocation history)."""
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            # Before test: status is unknown (fresh server, no caps or invocations)
            r0 = await client.get("/api/v1/resources/mcp_server/fs/status")
            assert r0.status_code == 200
            assert r0.json()["status"] == "unknown"

            # Run the /test endpoint — it should succeed and persist healthy state
            r_test = await client.post("/api/v1/resources/mcp_server/fs/test")
            assert r_test.status_code == 200, r_test.text
            assert r_test.json()["ok"] is True

            # After successful test: status must be 'healthy' from persisted state
            r1 = await client.get("/api/v1/resources/mcp_server/fs/status")
            assert r1.status_code == 200
            assert r1.json()["status"] == "healthy", (
                f"Expected 'healthy' after successful /test, got: {r1.json()}"
            )
    finally:
        await supervisor.dispose()
        await engine.dispose()


# ---------------------------------------------------------------------------
# T20 — get_server_status failing branch (last invocation status != "ok")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_server_status_failing_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /{name}/status must return 'failing' when the latest invocation has
    status != 'ok' and there is no persisted health record."""
    from datetime import UTC, datetime

    from coffer.domain.mcp.capability import MCPInvocation

    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)

    # Obtain the invocation repo to seed data directly
    from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
    from coffer.infrastructure.persistence.engine import session_maker

    sm = session_maker(engine)  # type: ignore[arg-type]
    inv_repo = MCPInvocationRepo(sm)

    # Seed a non-ok invocation for server "fs"
    await inv_repo.insert(
        MCPInvocation(
            id=None,
            timestamp=datetime.now(tz=UTC),
            resource_name="fs",
            capability_type="tool",
            capability_key="read_file",
            duration_ms=10,
            status="error",
            error_message="upstream died",
            session_id="test-session",
        )
    )

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            r = await client.get("/api/v1/resources/mcp_server/fs/status")
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "failing", (
                f"Expected 'failing' with non-ok last invocation, got: {r.json()}"
            )
    finally:
        await supervisor.dispose()
        await engine.dispose()


# ---------------------------------------------------------------------------
# T20 — /test endpoint for an HTTP-transport server
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="HTTP-transport MCP server round trip")
@pytest.mark.asyncio
async def test_test_endpoint_http_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /{name}/test must work for an HTTP-transport MCP server."""
    from tests.fixtures.fake_mcp_server import start_http_fake

    _with_in_memory(monkeypatch)

    # Start a real HTTP fake MCP server
    proc, port = start_http_fake(tools=["echo_tool"])
    try:
        # Build an app with an HTTP-transport server config
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
            name="http_svc",
            config={"transport": {"type": "http", "url": f"http://127.0.0.1:{port}/mcp"}},
            actor="test",
        )

        prefs_repo = MCPCapabilityPreferenceRepo(sm)
        supervisor = SubprocessSupervisor(
            upstream_factory=build_upstream,
            resource_service=rsvc,
            credential_resolver=CredentialResolver(KeyringAdapter()),
        )
        discovery = CapabilityDiscovery(
            resource_service=rsvc,
            supervisor=supervisor,
            preferences=prefs_repo,
            audit=audit,
        )
        health_repo = MCPServerHealthRepo(sm)

        set_active_token("test-token")
        app = FastAPI()
        err_handlers.register(app)
        app.include_router(capability_router)
        app.dependency_overrides[get_resource_service] = lambda: rsvc
        app.dependency_overrides[get_audit_service] = lambda: audit
        app.dependency_overrides[get_capability_discovery] = lambda: discovery
        app.dependency_overrides[get_preferences_repo] = lambda: prefs_repo
        app.dependency_overrides[get_invocation_repo] = lambda: MCPInvocationRepo(sm)
        app.dependency_overrides[get_health_repo] = lambda: health_repo
        app.dependency_overrides[get_credential_store] = lambda: _InMemoryCredentialStore()

        transport_obj = ASGITransport(app=app)
        try:
            async with AsyncClient(
                transport=transport_obj,
                base_url="http://test",
                headers={"X-Coffer-Token": "test-token"},
            ) as client:
                r = await client.post("/api/v1/resources/mcp_server/http_svc/test")
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["ok"] is True, f"HTTP-transport /test failed: {body}"
                assert body["latency_ms"] >= 0
        finally:
            await supervisor.dispose()
            await engine.dispose()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# T21 — refresh returns 404 for an unregistered server
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_unknown_server_returns_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/v1/resources/mcp_server/{name}/refresh for an unregistered
    server name must return HTTP 404 with envelope code RESOURCE_NOT_FOUND.
    """
    _with_in_memory(monkeypatch)
    app, engine, _rsvc, _prefs, supervisor = await _build_app(tmp_path)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Coffer-Token": "test-token"},
        ) as client:
            r = await client.post("/api/v1/resources/mcp_server/does_not_exist/refresh")
            assert r.status_code == 404, r.text
            body = r.json()
            assert "error" in body, f"Expected error envelope, got: {body}"
            assert body["error"]["code"] == "RESOURCE_NOT_FOUND", (
                f"Expected RESOURCE_NOT_FOUND, got: {body['error']['code']}"
            )
    finally:
        await supervisor.dispose()
        await engine.dispose()
