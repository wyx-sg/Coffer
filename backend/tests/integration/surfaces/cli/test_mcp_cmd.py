"""Integration tests for `coffer mcp ...` CLI subcommands (lifecycle verbs,
`add`, `test`, `cap`).

Strategy:
- Extend the shared ``in_proc_daemon`` fixture to also register the
  ``mcp_server`` kind and the MCP-specific HTTP routes.
- Use a stub ``CapabilityDiscovery`` so tests never spawn real
  subprocesses.
- Use a real ``MCPInvocationRepo`` backed by the in-memory SQLite DB.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC
from datetime import datetime as dt
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_registry import PrunableRegistry, PrunableTable
from coffer.application.retention_service import RetentionService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
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
from coffer.infrastructure.persistence.retention_repo import (
    FileRetentionRepo,
    allowlist_from_registry,
)
from coffer.surfaces.cli.main import app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_routes import router as daemon_router
from coffer.surfaces.http.dependencies import (
    get_audit_service,
    get_resource_service,
    get_retention_service,
)
from coffer.surfaces.http.mcp.capability_routes import router as capability_router
from coffer.surfaces.http.mcp.dependencies import (
    get_capability_discovery,
    get_health_repo,
    get_invocation_repo,
    get_preferences_repo,
)
from coffer.surfaces.http.mcp.invocation_routes import (
    aggregate_router as invocation_aggregate_router,
)
from coffer.surfaces.http.mcp.invocation_routes import router as invocation_router
from coffer.surfaces.http.mcp.page_routes import router as page_router
from coffer.surfaces.http.mcp.server_test_routes import router as server_test_router
from coffer.surfaces.http.resource_routes import router as resource_router
from coffer.surfaces.http.retention_routes import router as retention_router
from coffer.surfaces.http.secret_composition import get_secret_store
from tests.support.no_approvals import router as no_approvals_router
from tests.support.vault_stores import derived_sm, make_resource_repo

_runner = CliRunner()
_TOKEN = "test-token-mcp"
_PORT = 8100


class _FakeConfig(BaseModel):
    foo: int = 1


# ---------------------------------------------------------------------------
# Stub CapabilityDiscovery (never touches real subprocesses)
# ---------------------------------------------------------------------------


class _StubDiscovery:
    """Returns canned tool/resource/prompt lists, cached per server until
    ``invalidate`` — the way the real discovery cache behaves, so a test can
    tell a re-query from a cache hit. ``tools`` and ``unreachable`` are the
    upstream's state, which a test changes between commands."""

    def __init__(self) -> None:
        self._invalidated: set[str] = set()
        self.tools: list[str] = ["read_file"]
        self.prompts: list[str] = []
        self.unreachable = False
        self._cache: dict[str, list[str]] = {}
        #: Set by the fixture: ``(resource repo, preference repo)``, so the
        #: ``enabled`` flag reflects a toggle the way the real discovery's does.
        self.repos: tuple[Any, Any] | None = None

    async def _enabled(self, server_name: str, capability_type: str, key: str) -> bool:
        if self.repos is None:
            return True
        resources, prefs = self.repos
        resource = await resources.find_by_name("mcp_server", server_name)
        pref = None if resource is None else await prefs.find(resource.uid, capability_type, key)
        return True if pref is None else bool(pref.enabled)

    def invalidate(self, server_name: str) -> None:
        self._invalidated.add(server_name)
        self._cache.pop(server_name, None)

    async def list_tools(self, server_name: str, *, include_disabled: bool = False) -> list[Any]:
        from coffer.application.mcp.discovery import DiscoveredTool
        from coffer.domain.errors import UpstreamUnavailable

        if server_name not in self._cache:
            if self.unreachable:
                raise UpstreamUnavailable(f"{server_name} is down")
            self._cache[server_name] = list(self.tools)
        return [
            DiscoveredTool(
                prefixed_name=f"{server_name}__{tool}",
                original_name=tool,
                description=f"The {tool} tool",
                input_schema={},
                enabled=await self._enabled(server_name, "tool", tool),
            )
            for tool in self._cache[server_name]
        ]

    async def list_resources(
        self, server_name: str, *, include_disabled: bool = False
    ) -> list[Any]:
        from coffer.application.mcp.discovery import DiscoveredResource

        return [
            DiscoveredResource(
                prefixed_uri=f"{server_name}__file:///tmp/x",
                original_uri="file:///tmp/x",
                name="x",
                description=None,
                mime_type=None,
                enabled=True,
            )
        ]

    async def list_prompts(self, server_name: str, *, include_disabled: bool = False) -> list[Any]:
        from coffer.application.mcp.discovery import DiscoveredPrompt

        return [
            DiscoveredPrompt(
                prefixed_name=f"{server_name}__{prompt}",
                original_name=prompt,
                description=None,
                arguments=[],
                enabled=await self._enabled(server_name, "prompt", prompt),
            )
            for prompt in self.prompts
        ]


#: The stub the most recent ``mcp_daemon`` wired in, for tests that change what
#: the upstream offers between two commands.
STUB: dict[str, _StubDiscovery] = {}


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _build_mcp_app(tmp_path: Any) -> tuple[FastAPI, Any]:
    """Build a fully-wired app including mcp_server kind + MCP routes."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'mcp.db'}"
    engine = create_async_engine_with_pragmas(db_url)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create_tables(engine))

    sm = session_maker(engine)
    mcp_kind = Kind(
        name="mcp_server",
        display_name="MCP Server",
        config_schema=MCPServerConfig,
        # As production declares it: a server is shown by its fixed name and
        # carries no title (spec resource-framework "Carry an optional
        # editable title on the kinds that have one").
        titled=False,
    )
    kinds = {"mcp_server": mcp_kind}

    resource_repo = make_resource_repo()
    audit_repo = SqlAlchemyAuditRepo(sm)
    audit_svc = AuditService(audit_repo)
    resource_svc = ResourceService(kinds=kinds, repo=resource_repo, audit=audit_svc)

    registry = PrunableRegistry()
    registry.register(
        PrunableTable(
            name="audit_log",
            timestamp_column="timestamp",
            default_retention_days=365,
            display_name="Audit Log",
            description="Resource lifecycle events.",
        )
    )
    retention_repo = FileRetentionRepo(sm, allowlist=allowlist_from_registry(registry.all()))
    retention_svc = RetentionService(registry=registry, repo=retention_repo, audit=audit_svc)
    loop.run_until_complete(retention_svc.initialize_defaults())
    loop.close()

    prefs_repo = MCPCapabilityPreferenceStore(derived_sm())
    inv_repo = MCPInvocationRepo(sm)
    stub_discovery = _StubDiscovery()
    stub_discovery.repos = (resource_repo, prefs_repo)
    STUB["discovery"] = stub_discovery
    health_repo = MCPServerHealthRepo(derived_sm())

    fapp = FastAPI()
    err_handlers.register(fapp)
    fapp.include_router(daemon_router)
    fapp.include_router(resource_router)
    fapp.include_router(no_approvals_router)
    fapp.include_router(retention_router)
    fapp.include_router(capability_router)
    fapp.include_router(invocation_router)
    fapp.include_router(invocation_aggregate_router)
    fapp.include_router(server_test_router)
    fapp.include_router(page_router)

    fapp.dependency_overrides[get_resource_service] = lambda: resource_svc
    fapp.dependency_overrides[get_audit_service] = lambda: audit_svc
    fapp.dependency_overrides[get_retention_service] = lambda: retention_svc
    fapp.dependency_overrides[get_capability_discovery] = lambda: stub_discovery
    fapp.dependency_overrides[get_preferences_repo] = lambda: prefs_repo
    fapp.dependency_overrides[get_invocation_repo] = lambda: inv_repo
    fapp.dependency_overrides[get_health_repo] = lambda: health_repo
    fapp.dependency_overrides[get_secret_store] = lambda: None

    set_active_token(_TOKEN)
    return fapp, engine


@pytest.fixture
def mcp_daemon(tmp_path: Any, monkeypatch: Any) -> Any:
    """In-process daemon fixture extended with mcp_server kind + routes."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'mcp.db'}")
    orig_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)

    fapp, _engine = _build_mcp_app(tmp_path)

    daemon_json_dir = home / ".coffer"
    daemon_json_dir.mkdir(parents=True, exist_ok=True)
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=_PORT,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
    )
    write(home / ".coffer" / "daemon.json", info)

    fake_client = TestClient(
        fapp,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )

    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda **_kw: (fake_client, info))

    yield home

    set_active_token(None)
    if orig_home is not None:
        os.environ["HOME"] = orig_home
    elif "HOME" in os.environ:
        del os.environ["HOME"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_server(name: str = "fs", transport: str = "stdio") -> str:
    """Register a server and hand back its uid.

    Every caller that seeds a row keyed on identity — a preference, an
    invocation — needs it, and a uid is minted rather than chosen, so it can
    only come from the registration that made it.
    """
    from coffer.surfaces.cli import _client as _cli_client

    client, _ = _cli_client.client_or_exit()
    if transport == "stdio":
        config: dict[str, Any] = {
            "transport": {
                "type": "stdio",
                "command": "cat",
                "args": [],
            }
        }
    else:
        config = {
            "transport": {
                "type": "http",
                "url": "http://localhost:9000",
            }
        }
    r = client.post(
        "/resources",
        json={"kind": "mcp_server", "name": name, "config": config},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


# ---------------------------------------------------------------------------
# coffer mcp test — refresh, then the health test. The upstream connection is
# faked at the route's seam, so the real route (and its health write) runs.
# ---------------------------------------------------------------------------


def _fake_upstream(monkeypatch: pytest.MonkeyPatch, *, answers: bool) -> None:
    from coffer.infrastructure.mcp import probe as server_probe

    class _Conn:
        def __init__(self, **_kw: Any) -> None:
            pass

        async def spawn_and_initialize(self) -> dict[str, Any]:
            if not answers:
                raise RuntimeError("connection refused")
            return {"tools": {}}

        async def request(self, method: str, params: dict[str, Any]) -> Any:
            return type("Listed", (), {"tools": []})()

        async def close(self) -> None:
            return None

    monkeypatch.setattr(server_probe, "StdioUpstreamConnection", _Conn)
    # The fake command is not on PATH; the probe's pre-spawn check is not under test.
    monkeypatch.setattr(server_probe, "_launcher_problem", lambda *_a: None)


def _tool_names(uid: str) -> list[str]:
    from coffer.surfaces.cli import _client as _cli_client

    client, _ = _cli_client.client_or_exit()
    r = client.get(f"/resources/mcp_server/{uid}/capabilities")
    assert r.status_code == 200, r.text
    return [t["original_name"] for t in r.json()["tools"]]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="test re-queries capabilities before reporting health"
)
def test_mcp_test_requeries_capabilities_then_reports_health(
    mcp_daemon: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = _register_server()
    assert _tool_names(uid) == ["read_file"]

    # The upstream gains a tool; Coffer's cached view does not know yet.
    STUB["discovery"].tools.append("write_file")
    assert _tool_names(uid) == ["read_file"]

    _fake_upstream(monkeypatch, answers=True)
    result = _runner.invoke(app, ["mcp", "test", "fs"])
    assert result.exit_code == 0, result.output
    assert "2 tools" in result.output and "re-queried" in result.output
    assert "OK" in result.output

    assert _tool_names(uid) == ["read_file", "write_file"]

    # An unreachable upstream: the command exits non-zero and names the failure.
    STUB["discovery"].unreachable = True
    _fake_upstream(monkeypatch, answers=False)
    down = _runner.invoke(app, ["mcp", "test", "fs"])
    combined = down.output + (down.stderr or "")
    assert down.exit_code == 7, combined
    assert "FAIL" in combined and "did not complete MCP initialize" in combined


def test_mcp_test_not_found_exit_4(mcp_daemon: Any) -> None:
    """An unknown NAME fails at the lookup — the CLI names what the user typed."""
    result = _runner.invoke(app, ["mcp", "test", "ghost"])
    assert result.exit_code == 4, result.output
    assert "no mcp_server named 'ghost'" in (result.output + (result.stderr or ""))
