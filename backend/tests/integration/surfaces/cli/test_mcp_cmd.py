"""Integration tests for `coffer mcp ...` CLI subcommands.

Strategy:
- Extend the shared ``in_proc_daemon`` fixture to also register the
  ``mcp_server`` kind and the MCP-specific HTTP routes.
- Use a stub ``CapabilityDiscovery`` so tests never spawn real
  subprocesses.
- Use a real ``MCPInvocationRepo`` backed by the in-memory SQLite DB.
"""

from __future__ import annotations

import asyncio
import json
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
from coffer.application.retention_service import RetentionService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
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
    SqlAlchemyRetentionRepo,
)
from coffer.infrastructure.persistence.retention import PrunableRegistry, PrunableTable
from coffer.surfaces.cli.main import app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_routes import router as daemon_router
from coffer.surfaces.http.dependencies import (
    get_audit_service,
    get_capability_discovery,
    get_invocation_repo,
    get_preferences_repo,
    get_resource_service,
    get_retention_service,
)
from coffer.surfaces.http.mcp.capability_routes import router as capability_router
from coffer.surfaces.http.mcp.invocation_routes import router as invocation_router
from coffer.surfaces.http.resource_routes import router as resource_router
from coffer.surfaces.http.retention_routes import router as retention_router

_runner = CliRunner()
_TOKEN = "test-token-mcp"
_PORT = 8100


class _FakeConfig(BaseModel):
    foo: int = 1


# ---------------------------------------------------------------------------
# Stub CapabilityDiscovery (never touches real subprocesses)
# ---------------------------------------------------------------------------


class _StubDiscovery:
    """Returns canned tool/resource/prompt lists."""

    def __init__(self) -> None:
        self._invalidated: set[str] = set()

    def invalidate(self, server_name: str) -> None:
        self._invalidated.add(server_name)

    async def list_tools(self, server_name: str, *, include_disabled: bool = False) -> list[Any]:
        from coffer.application.mcp.discovery import DiscoveredTool

        return [
            DiscoveredTool(
                prefixed_name=f"{server_name}__read_file",
                original_name="read_file",
                description="Read a file",
                input_schema={},
                enabled=True,
            )
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
        return []


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
    )
    kinds = {"mcp_server": mcp_kind}

    resource_repo = SqlAlchemyResourceRepo(sm)
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
    retention_repo = SqlAlchemyRetentionRepo(sm)
    retention_svc = RetentionService(registry=registry, repo=retention_repo, audit=audit_svc)
    loop.run_until_complete(retention_svc.initialize_defaults())
    loop.close()

    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    inv_repo = MCPInvocationRepo(sm)
    stub_discovery = _StubDiscovery()

    fapp = FastAPI()
    err_handlers.register(fapp)
    fapp.include_router(daemon_router)
    fapp.include_router(resource_router)
    fapp.include_router(retention_router)
    fapp.include_router(capability_router)
    fapp.include_router(invocation_router)

    fapp.dependency_overrides[get_resource_service] = lambda: resource_svc
    fapp.dependency_overrides[get_audit_service] = lambda: audit_svc
    fapp.dependency_overrides[get_retention_service] = lambda: retention_svc
    fapp.dependency_overrides[get_capability_discovery] = lambda: stub_discovery
    fapp.dependency_overrides[get_preferences_repo] = lambda: prefs_repo
    fapp.dependency_overrides[get_invocation_repo] = lambda: inv_repo

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
        binary_path="/test",
    )
    write(home / ".coffer" / "daemon.json", info)

    fake_client = TestClient(
        fapp,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )

    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, info))

    yield home

    set_active_token(None)
    if orig_home is not None:
        os.environ["HOME"] = orig_home
    elif "HOME" in os.environ:
        del os.environ["HOME"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_server(name: str = "fs", transport: str = "stdio") -> None:
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


# ---------------------------------------------------------------------------
# coffer mcp add
# ---------------------------------------------------------------------------


def test_mcp_add_stdio(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "cat -n"])
    assert result.exit_code == 0, result.output
    assert "registered: mcp_server:fs" in result.output


def test_mcp_add_http(mcp_daemon: Any) -> None:
    result = _runner.invoke(
        app,
        [
            "mcp",
            "add",
            "remote",
            "--http",
            "http://example.com/mcp",
            "--credential",
            "Authorization=keychain:myref",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "registered: mcp_server:remote" in result.output


def test_mcp_add_both_flags_exits_2(mcp_daemon: Any) -> None:
    result = _runner.invoke(
        app,
        ["mcp", "add", "fs", "--stdio", "cat", "--http", "http://x.com"],
    )
    assert result.exit_code == 2


def test_mcp_add_neither_flag_exits_2(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "add", "fs"])
    assert result.exit_code == 2


def test_mcp_add_duplicate_exits_5(mcp_daemon: Any) -> None:
    _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "cat"])
    result = _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "cat"])
    assert result.exit_code == 5


def _patch_add_route(monkeypatch: Any, *, status: int, body: dict[str, Any]) -> None:
    """Mount a stub POST /resources that returns a fixed status + JSON body so
    the `add` command's 400/422 error branches can be exercised."""
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse

    from coffer.infrastructure.daemon.pid_lock import DaemonInfo
    from coffer.surfaces.http import errors as _err
    from coffer.surfaces.http.auth import set_active_token as _set_token

    router = APIRouter(prefix="/api/v1")

    @router.post("/resources")
    async def _create() -> JSONResponse:  # type: ignore[no-untyped-def]
        return JSONResponse(status_code=status, content=body)

    stub_app = FastAPI()
    _err.register(stub_app)
    stub_app.include_router(router)
    _set_token("stub-token")
    info = DaemonInfo(
        version=1,
        pid=1,
        port=9999,
        token="stub-token",
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    client = TestClient(
        stub_app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": "stub-token"},
        raise_server_exceptions=False,
    )
    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))


def test_mcp_add_http_400_exits_6(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 400 from the daemon surfaces the error message and exits 6."""
    _patch_add_route(
        monkeypatch,
        status=400,
        body={"error": {"message": "bad transport"}},
    )
    result = _runner.invoke(app, ["mcp", "add", "fs", "--http", "http://x.com"])
    assert result.exit_code == 6, result.output
    assert "bad transport" in (result.output + (result.stderr or ""))


def test_mcp_add_config_422_exits_6(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 422 (config invalid) from the daemon exits 6."""
    _patch_add_route(
        monkeypatch,
        status=422,
        body={"error": {"message": "config invalid", "fields": ["url"]}},
    )
    result = _runner.invoke(app, ["mcp", "add", "fs", "--http", "http://x.com"])
    assert result.exit_code == 6, result.output
    assert "config invalid" in (result.output + (result.stderr or ""))


def test_mcp_add_no_auto_enable(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "cat", "--no-auto-enable"])
    assert result.exit_code == 0, result.output
    # Verify the flag was persisted
    from coffer.surfaces.cli import _client as _cli_client

    client, _ = _cli_client.client_or_exit()
    r = client.get("/resources/mcp_server/fs")
    assert r.status_code == 200
    assert r.json()["config"]["auto_enable_new_capabilities"] is False


# ---------------------------------------------------------------------------
# coffer mcp list
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="CLI returns non-zero exit on daemon unreachable"
)
def test_mcp_list_exits_3_when_daemon_unreachable(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No daemon.json + spawn timeout => `coffer mcp list` exits with code 3
    and prints a daemon-unreachable hint to stderr/stdout.

    ADR-006: client_or_exit() now auto-spawns; we prevent the real spawn and
    simulate a timeout so the error path (exit 3) is exercised.
    """
    from coffer.surfaces.cli import _client as cli_client

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli_client, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)

    result = _runner.invoke(app, ["mcp", "list"])
    assert result.exit_code == 3, result.output
    combined = result.output + (result.stderr or "")
    assert "daemon" in combined.lower()


def test_mcp_list_empty(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "list", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data == {"resources": []}


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="CLI --json output is machine-readable")
def test_mcp_list_shows_registered(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # Stable top-level key per spec scenario: `resources` for `mcp list`.
    assert isinstance(payload, dict), "expected object with stable top-level keys"
    assert list(payload.keys()) == ["resources"], (
        f"expected only 'resources' key, got {list(payload.keys())}"
    )
    items = payload["resources"]
    assert len(items) == 1
    assert items[0]["name"] == "fs"
    # Machine-readable: pure JSON, no human framing (table headers, ANSI).
    assert "\x1b[" not in result.output, "ANSI escape leaked into --json output"


def test_mcp_list_table(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "list"])
    assert result.exit_code == 0, result.output
    assert "fs" in result.output


# ---------------------------------------------------------------------------
# coffer mcp show
# ---------------------------------------------------------------------------


def test_mcp_show_existing(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "show", "fs"])
    assert result.exit_code == 0, result.output
    assert "mcp_server:fs" in result.output


def test_mcp_show_json(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "show", "fs", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["name"] == "fs"


def test_mcp_show_not_found(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "show", "nope"])
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# coffer mcp remove
# ---------------------------------------------------------------------------


def test_mcp_remove_with_force(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "remove", "fs", "--force"])
    assert result.exit_code == 0, result.output
    assert "removed: mcp_server:fs" in result.output

    result2 = _runner.invoke(app, ["mcp", "show", "fs"])
    assert result2.exit_code == 4


def test_mcp_remove_not_found_with_force(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "remove", "ghost", "--force"])
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# coffer mcp refresh
# ---------------------------------------------------------------------------


def test_mcp_refresh(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "refresh", "fs"])
    assert result.exit_code == 0, result.output
    assert "refreshed: mcp_server:fs" in result.output


def test_mcp_refresh_not_found(mcp_daemon: Any) -> None:
    """POST /refresh on an unknown server must return 404 → CLI exit 4."""
    result = _runner.invoke(app, ["mcp", "refresh", "ghost"])
    assert result.exit_code == 4, (
        f"Expected exit 4 (NOT_FOUND) for refresh of unknown server, got {result.exit_code}:\n"
        f"{result.output}"
    )


# ---------------------------------------------------------------------------
# coffer mcp tool list / enable / disable
# ---------------------------------------------------------------------------


def test_mcp_tool_list_json(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "tool", "list", "fs", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # Stable top-level key per spec scenario: `tools` for `mcp tool list`.
    assert isinstance(payload, dict)
    tools = payload["tools"]
    assert any(t["original_name"] == "read_file" for t in tools)


def test_mcp_tool_list_table(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "tool", "list", "fs"])
    assert result.exit_code == 0, result.output
    # The rendered table must actually contain the discovered tool — exit_code
    # alone would pass even if the table rendered empty/wrong.
    assert "read_file" in result.output


def test_mcp_tool_enable_disable(mcp_daemon: Any) -> None:
    """Disable/enable a tool via CLI — unconditional assertions after seeding the pref row."""
    _register_server()

    # Seed the capability preference row directly via the DB so disable/enable can proceed.
    # The prefs table row is created by CapabilityDiscovery.insert() — we replicate that here
    # using the same DB URL the mcp_daemon fixture wired up.
    from datetime import UTC, datetime

    from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceRepo
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )

    db_url = os.environ["COFFER_DB_URL"]
    engine = create_async_engine_with_pragmas(db_url)

    async def _seed() -> int:
        sm2 = session_maker(engine)
        prefs = MCPCapabilityPreferenceRepo(sm2)
        # Find the resource id for "fs"
        from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo

        repo = SqlAlchemyResourceRepo(sm2)
        from coffer.domain.resource import ResourceRef

        resource = await repo.find(ResourceRef("mcp_server", "fs"))
        assert resource is not None, "resource 'fs' not found in DB"
        now = datetime.now(tz=UTC)
        await prefs.insert(resource.id, "tool", "read_file", True, now, now)
        await engine.dispose()
        return resource.id

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()

    # Now the preference row exists — disable it via CLI
    result = _runner.invoke(app, ["mcp", "tool", "disable", "fs", "read_file"])
    assert result.exit_code == 0, result.output
    assert "disabled" in result.output

    # Re-enable it via CLI
    result2 = _runner.invoke(app, ["mcp", "tool", "enable", "fs", "read_file"])
    assert result2.exit_code == 0, result2.output
    assert "enabled" in result2.output


def test_mcp_resource_enable_disable_uri_with_slashes(mcp_daemon: Any) -> None:
    """CODE-038: a resource capability key is a URI containing '/' (e.g.
    file:///etc/hosts). The CLI must send it in the request body, not the URL
    path — the old path-style route can't match multi-segment keys and 404s.
    """
    _register_server()

    from datetime import UTC, datetime

    from coffer.domain.resource import ResourceRef
    from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceRepo
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )
    from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo

    uri = "file:///etc/hosts"
    db_url = os.environ["COFFER_DB_URL"]
    engine = create_async_engine_with_pragmas(db_url)

    async def _seed() -> None:
        sm2 = session_maker(engine)
        repo = SqlAlchemyResourceRepo(sm2)
        resource = await repo.find(ResourceRef("mcp_server", "fs"))
        assert resource is not None
        now = datetime.now(tz=UTC)
        await MCPCapabilityPreferenceRepo(sm2).insert(resource.id, "resource", uri, True, now, now)
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()

    # Disable then enable the slash-containing resource key via CLI.
    disabled = _runner.invoke(app, ["mcp", "resource", "disable", "fs", uri])
    assert disabled.exit_code == 0, disabled.output
    assert "disabled" in disabled.output

    enabled = _runner.invoke(app, ["mcp", "resource", "enable", "fs", uri])
    assert enabled.exit_code == 0, enabled.output
    assert "enabled" in enabled.output


# ---------------------------------------------------------------------------
# coffer mcp invocations
# ---------------------------------------------------------------------------


def test_mcp_invocations_empty(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "invocations", "fs", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data == {"invocations": []}


def test_mcp_invocations_table(mcp_daemon: Any) -> None:
    _register_server()

    # Seed an invocation row so the table renders real content (not an empty
    # table that a bare exit_code check would still pass).
    from datetime import UTC, datetime

    from coffer.domain.mcp.capability import MCPInvocation
    from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )

    engine = create_async_engine_with_pragmas(os.environ["COFFER_DB_URL"])

    async def _seed() -> None:
        await MCPInvocationRepo(session_maker(engine)).insert(
            MCPInvocation(
                id=None,
                timestamp=datetime.now(tz=UTC),
                resource_name="fs",
                capability_type="tool",
                capability_key="read_file",
                duration_ms=12,
                status="ok",
                error_message=None,
                session_id="s1",
            )
        )
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()

    result = _runner.invoke(app, ["mcp", "invocations", "fs"])
    assert result.exit_code == 0, result.output
    # The seeded invocation's capability key must appear in the rendered table.
    assert "read_file" in result.output


# ---------------------------------------------------------------------------
# coffer mcp add — flag-parsing / error branches
# ---------------------------------------------------------------------------


def test_mcp_add_empty_stdio_exits_2(mcp_daemon: Any) -> None:
    """`--stdio ''` parses to an empty argv → exit 2 with a clear message."""
    result = _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "   "])
    assert result.exit_code == 2, result.output
    assert "cannot be empty" in (result.output + (result.stderr or ""))


def test_mcp_add_bad_credential_format_exits_2(mcp_daemon: Any) -> None:
    """A `--credential` value without '=' is a typer.BadParameter → exit 2."""
    result = _runner.invoke(
        app,
        ["mcp", "add", "fs", "--stdio", "cat", "--credential", "NO_EQUALS_SIGN"],
    )
    assert result.exit_code == 2, result.output
    assert "credential" in (result.output + (result.stderr or "")).lower()


# ---------------------------------------------------------------------------
# coffer mcp invocations — limit / status filter / since / 404
# ---------------------------------------------------------------------------


def _seed_invocations() -> None:
    """Seed three invocation rows (two ok, one error) for server 'fs'."""
    from datetime import UTC, datetime

    from coffer.domain.mcp.capability import MCPInvocation
    from coffer.infrastructure.mcp.persistence import MCPInvocationRepo
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )

    engine = create_async_engine_with_pragmas(os.environ["COFFER_DB_URL"])

    async def _seed() -> None:
        repo = MCPInvocationRepo(session_maker(engine))
        now = datetime.now(tz=UTC)
        await repo.insert(
            MCPInvocation(
                id=None,
                timestamp=now,
                resource_name="fs",
                capability_type="tool",
                capability_key="read_file",
                duration_ms=5,
                status="ok",
                error_message=None,
                session_id="s1",
            )
        )
        await repo.insert(
            MCPInvocation(
                id=None,
                timestamp=now,
                resource_name="fs",
                capability_type="tool",
                capability_key="write_file",
                duration_ms=7,
                status="error",
                error_message="boom",
                session_id="s2",
            )
        )
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()


def test_mcp_invocations_json_shape(mcp_daemon: Any) -> None:
    """`--json` returns an object whose sole top-level key is `invocations`."""
    _register_server()
    _seed_invocations()
    result = _runner.invoke(app, ["mcp", "invocations", "fs", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert list(payload.keys()) == ["invocations"]
    keys = {inv["capability_key"] for inv in payload["invocations"]}
    assert keys == {"read_file", "write_file"}
    assert "\x1b[" not in result.output, "ANSI escape leaked into --json output"


def test_mcp_invocations_status_filter(mcp_daemon: Any) -> None:
    """`--status error` filters server-side to only the error row."""
    _register_server()
    _seed_invocations()
    result = _runner.invoke(app, ["mcp", "invocations", "fs", "--status", "error", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    invs = payload["invocations"]
    assert len(invs) == 1
    assert invs[0]["capability_key"] == "write_file"
    assert invs[0]["status"] == "error"


def test_mcp_invocations_since_passed_through(mcp_daemon: Any) -> None:
    """A `--since` far in the future filters out every seeded row."""
    _register_server()
    _seed_invocations()
    result = _runner.invoke(
        app,
        ["mcp", "invocations", "fs", "--since", "2999-01-01T00:00:00+00:00", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {"invocations": []}


def test_mcp_invocations_limit_validation_exits_2(mcp_daemon: Any) -> None:
    """`--limit 0` violates the min=1 constraint → typer exits 2."""
    _register_server()
    result = _runner.invoke(app, ["mcp", "invocations", "fs", "--limit", "0"])
    assert result.exit_code == 2, result.output


def test_mcp_invocations_not_found_exits_4(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the invocations endpoint 404s, the CLI maps it to exit 4."""
    from fastapi import APIRouter, HTTPException

    from coffer.infrastructure.daemon.pid_lock import DaemonInfo
    from coffer.surfaces.http import errors as _err
    from coffer.surfaces.http.auth import set_active_token as _set_token

    router = APIRouter(prefix="/api/v1/resources/mcp_server")

    @router.get("/{name}/invocations")
    async def _inv(name: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        raise HTTPException(status_code=404, detail="not found")

    stub_app = FastAPI()
    _err.register(stub_app)
    stub_app.include_router(router)
    _set_token("stub-token")
    info = DaemonInfo(
        version=1,
        pid=1,
        port=9999,
        token="stub-token",
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    client = TestClient(
        stub_app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": "stub-token"},
        raise_server_exceptions=False,
    )
    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))

    result = _runner.invoke(app, ["mcp", "invocations", "ghost"])
    assert result.exit_code == 4, result.output
    assert "not found" in (result.output + (result.stderr or ""))


# ---------------------------------------------------------------------------
# coffer mcp remove — interactive confirmation decline
# ---------------------------------------------------------------------------


def test_mcp_remove_declined_confirmation_exits_1(mcp_daemon: Any) -> None:
    """Answering 'n' at the confirm prompt (no --force) aborts with exit 1
    and leaves the server registered."""
    _register_server()
    result = _runner.invoke(app, ["mcp", "remove", "fs"], input="n\n")
    assert result.exit_code == 1, result.output

    still = _runner.invoke(app, ["mcp", "show", "fs"])
    assert still.exit_code == 0, still.output


# ---------------------------------------------------------------------------
# coffer mcp test — uses a stubbed /test route so the CLI's success/failure
# branches (exit 0 vs exit 7) and the 404 branch are exercised genuinely.
# ---------------------------------------------------------------------------


def _patch_test_route(monkeypatch: Any, *, ok: bool) -> None:
    """Mount a tiny app whose POST /{name}/test returns a canned result and
    whose 404 is driven by a known-vs-unknown server name. Rewires
    ``client_or_exit`` to point the CLI at it."""
    from fastapi import APIRouter

    from coffer.infrastructure.daemon.pid_lock import DaemonInfo
    from coffer.surfaces.http import errors as _err
    from coffer.surfaces.http.auth import set_active_token as _set_token
    from coffer.surfaces.http.schemas import McpTestResultOut

    _known = {"fs"}
    router = APIRouter(prefix="/api/v1/resources/mcp_server", tags=["mcp"])

    @router.post("/{name}/test", response_model=McpTestResultOut)
    async def _test(name: str) -> McpTestResultOut:  # type: ignore[no-untyped-def]
        if name not in _known:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="not found")
        if ok:
            return McpTestResultOut(ok=True, latency_ms=42, protocol_version="2025-06-18")
        return McpTestResultOut(ok=False, latency_ms=9, error_message="upstream down")

    stub_app = FastAPI()
    _err.register(stub_app)
    stub_app.include_router(router)
    _set_token("stub-token")

    info = DaemonInfo(
        version=1,
        pid=1,
        port=9999,
        token="stub-token",
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    client = TestClient(
        stub_app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": "stub-token"},
        raise_server_exceptions=False,
    )
    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (client, info))


def test_mcp_test_ok_exit_0(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_test_route(monkeypatch, ok=True)
    result = _runner.invoke(app, ["mcp", "test", "fs"])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output
    assert "42" in result.output


def test_mcp_test_fail_exit_7(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_test_route(monkeypatch, ok=False)
    result = _runner.invoke(app, ["mcp", "test", "fs"])
    assert result.exit_code == 7, result.output
    combined = result.output + (result.stderr or "")
    assert "FAIL" in combined
    assert "upstream down" in combined


def test_mcp_test_not_found_exit_4(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_test_route(monkeypatch, ok=True)
    result = _runner.invoke(app, ["mcp", "test", "ghost"])
    assert result.exit_code == 4, result.output
