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
from coffer.application.retention_registry import PrunableRegistry, PrunableTable
from coffer.application.retention_service import RetentionService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
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
    SqlAlchemyRetentionRepo,
)
from coffer.infrastructure.persistence.retention_repo import allowlist_from_registry
from coffer.surfaces.cli.main import app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.credential_composition import get_credential_store
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
from coffer.surfaces.http.mcp.server_test_routes import router as server_test_router
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
        pref = None if resource is None else await prefs.find(resource.id, capability_type, key)
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
    retention_repo = SqlAlchemyRetentionRepo(sm, allowlist=allowlist_from_registry(registry.all()))
    retention_svc = RetentionService(registry=registry, repo=retention_repo, audit=audit_svc)
    loop.run_until_complete(retention_svc.initialize_defaults())
    loop.close()

    prefs_repo = MCPCapabilityPreferenceRepo(sm)
    inv_repo = MCPInvocationRepo(sm)
    stub_discovery = _StubDiscovery()
    stub_discovery.repos = (resource_repo, prefs_repo)
    STUB["discovery"] = stub_discovery
    health_repo = MCPServerHealthRepo(sm)

    fapp = FastAPI()
    err_handlers.register(fapp)
    fapp.include_router(daemon_router)
    fapp.include_router(resource_router)
    fapp.include_router(retention_router)
    fapp.include_router(capability_router)
    fapp.include_router(invocation_router)
    fapp.include_router(invocation_aggregate_router)
    fapp.include_router(server_test_router)

    fapp.dependency_overrides[get_resource_service] = lambda: resource_svc
    fapp.dependency_overrides[get_audit_service] = lambda: audit_svc
    fapp.dependency_overrides[get_retention_service] = lambda: retention_svc
    fapp.dependency_overrides[get_capability_discovery] = lambda: stub_discovery
    fapp.dependency_overrides[get_preferences_repo] = lambda: prefs_repo
    fapp.dependency_overrides[get_invocation_repo] = lambda: inv_repo
    fapp.dependency_overrides[get_health_repo] = lambda: health_repo
    fapp.dependency_overrides[get_credential_store] = lambda: None

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
# coffer mcp add
# ---------------------------------------------------------------------------


def test_mcp_add_stdio(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "cat -n"])
    assert result.exit_code == 0, result.output
    assert "registered: mcp_server fs" in result.output


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
    assert "registered: mcp_server remote" in result.output


def test_mcp_add_both_flags_exits_2(mcp_daemon: Any) -> None:
    result = _runner.invoke(
        app,
        ["mcp", "add", "fs", "--stdio", "cat", "--http", "http://x.com"],
    )
    assert result.exit_code == 2


def test_mcp_add_neither_flag_exits_2(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "add", "fs"])
    assert result.exit_code == 2


def test_mcp_add_over_long_title_registers_nothing(mcp_daemon: Any) -> None:
    """A refused --title is refused before the server is registered, so the
    corrected command can simply be run again."""
    result = _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "cat", "--title", "x" * 81])
    assert result.exit_code == 6
    assert "at most 80 characters" in result.output
    assert _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "cat"]).exit_code == 0


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


# ---------------------------------------------------------------------------
# coffer mcp list
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="CLI returns non-zero exit on daemon unreachable"
)
def test_mcp_list_exits_3_when_daemon_unreachable(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No daemon.json + spawn timeout => `coffer mcp list` exits with code 3
    and prints a daemon-unreachable hint to stderr/stdout.

    Detect-or-spawn: client_or_exit() now auto-spawns; we prevent the real spawn and
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


@pytest.mark.acceptance(spec="mcp-gateway", scenario="CLI --json output is machine-readable")
def test_mcp_list_and_log_mcp_json_are_machine_readable(mcp_daemon: Any) -> None:
    _seed_invocations(_register_server())
    for argv, key in (
        (["mcp", "list", "--json"], "resources"),
        (["log", "mcp", "--json"], "invocations"),
    ):
        result = _runner.invoke(app, argv)
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        # Stable top-level key per spec scenario, and nothing else.
        assert list(payload.keys()) == [key], f"{argv}: {list(payload.keys())}"
        assert payload[key], f"{argv} printed no rows"
        # Machine-readable: pure JSON, no human framing (table headers, ANSI).
        assert "\x1b[" not in result.output, "ANSI escape leaked into --json output"
    listed = json.loads(_runner.invoke(app, ["mcp", "list", "--json"]).output)["resources"]
    assert [item["name"] for item in listed] == ["fs"]


def test_mcp_list_table(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "list"])
    assert result.exit_code == 0, result.output
    assert "fs" in result.output


# ---------------------------------------------------------------------------
# coffer mcp show / edit (generated lifecycle verbs)
# ---------------------------------------------------------------------------


def test_mcp_show_existing(mcp_daemon: Any) -> None:
    uid = _register_server()
    result = _runner.invoke(app, ["mcp", "show", "fs"])
    assert result.exit_code == 0, result.output
    # Name AND uid: `show` is where a person goes for the address itself.
    assert "name:         fs" in result.output
    assert uid in result.output


def test_mcp_show_json(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "show", "fs", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["name"] == "fs"


def test_mcp_show_not_found(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "show", "nope"])
    assert result.exit_code == 4


def test_mcp_list_table_names_the_transport(mcp_daemon: Any) -> None:
    _register_server("remote", transport="http")
    result = _runner.invoke(app, ["mcp", "list"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    line = next(ln for ln in result.output.splitlines() if "remote" in ln)
    assert "http" in line


def test_mcp_edit_title_keeps_the_name(mcp_daemon: Any) -> None:
    uid = _register_server()
    result = _runner.invoke(app, ["mcp", "edit", "fs", "--title", "Files"])
    assert result.exit_code == 0, result.output
    shown = json.loads(_runner.invoke(app, ["mcp", "show", uid, "--json"]).output)
    assert (shown["name"], shown["title"]) == ("fs", "Files")


def _config_of(uid: str) -> dict[str, Any]:
    shown = json.loads(_runner.invoke(app, ["mcp", "show", uid, "--json"]).output)
    return dict(shown["config"])


def _edit(*args: str) -> Any:
    return _runner.invoke(app, ["mcp", "edit", "fs", *args])


def test_mcp_edit_stdio_replaces_the_command_line_only(mcp_daemon: Any) -> None:
    uid = _register_server()
    assert _edit("--env", "LOG=debug", "--credential", "TOKEN=mcp_server/x/TOKEN").exit_code == 0
    result = _edit("--stdio", "npx -y my-server --flag")
    assert result.exit_code == 0, result.output
    transport = _config_of(uid)["transport"]
    assert (transport["command"], transport["args"]) == ("npx", ["-y", "my-server", "--flag"])
    assert transport["env"] == {"LOG": "debug"}
    assert transport["credential_refs"] == {"TOKEN": "mcp_server/x/TOKEN"}


def test_mcp_edit_env_merges_and_clear_env_drops_the_rest(mcp_daemon: Any) -> None:
    uid = _register_server()
    assert _edit("--env", "A=1", "--env", "B=2").exit_code == 0
    assert _edit("--env", "B=3").exit_code == 0
    assert _config_of(uid)["transport"]["env"] == {"A": "1", "B": "3"}
    assert _edit("--clear-env", "--env", "C=4").exit_code == 0
    assert _config_of(uid)["transport"]["env"] == {"C": "4"}


def test_mcp_edit_credentials_merge_and_clear(mcp_daemon: Any) -> None:
    uid = _register_server()
    assert _edit("--credential", "A=ref/a", "--credential", "B=ref/b").exit_code == 0
    assert _config_of(uid)["transport"]["credential_refs"] == {"A": "ref/a", "B": "ref/b"}
    assert _edit("--clear-credentials").exit_code == 0
    assert _config_of(uid)["transport"]["credential_refs"] == {}


def test_mcp_edit_cwd_sets_and_empty_clears(mcp_daemon: Any) -> None:
    uid = _register_server()
    assert _edit("--cwd", "/tmp/work").exit_code == 0
    assert _config_of(uid)["transport"]["cwd"] == "/tmp/work"
    assert _edit("--cwd", "").exit_code == 0
    assert _config_of(uid)["transport"]["cwd"] is None


def test_mcp_edit_timeouts_keep_the_transport(mcp_daemon: Any) -> None:
    uid = _register_server()
    before = _config_of(uid)["transport"]
    result = _edit("--spawn-timeout-seconds", "60", "--request-timeout-seconds", "600")
    assert result.exit_code == 0, result.output
    config = _config_of(uid)
    assert (config["spawn_timeout_seconds"], config["request_timeout_seconds"]) == (60, 600)
    assert config["transport"] == before


def test_mcp_edit_timeout_out_of_bounds_is_refused(mcp_daemon: Any) -> None:
    uid = _register_server()
    result = _edit("--spawn-timeout-seconds", "1")
    assert result.exit_code != 0
    assert _config_of(uid).get("spawn_timeout_seconds", 30) == 30


def test_mcp_edit_http_url_and_headers(mcp_daemon: Any) -> None:
    uid = _register_server(transport="http")
    result = _edit("--http", "https://example.com/mcp", "--header", "X-Team=core")
    assert result.exit_code == 0, result.output
    transport = _config_of(uid)["transport"]
    assert transport["url"].rstrip("/") == "https://example.com/mcp"
    assert transport["headers"] == {"X-Team": "core"}
    assert _edit("--clear-headers").exit_code == 0
    assert _config_of(uid)["transport"]["headers"] == {}


def test_mcp_edit_switches_transport_keeping_credentials(mcp_daemon: Any) -> None:
    uid = _register_server()
    assert _edit("--env", "A=1", "--credential", "TOKEN=ref/t").exit_code == 0
    result = _edit("--http", "https://example.com/mcp")
    assert result.exit_code == 0, result.output
    transport = _config_of(uid)["transport"]
    assert transport["type"] == "http"
    assert transport["credential_refs"] == {"TOKEN": "ref/t"}
    assert "env" not in transport and "command" not in transport
    assert _edit("--stdio", "cat").exit_code == 0
    assert _config_of(uid)["transport"]["type"] == "stdio"


def test_mcp_edit_refuses_a_flag_of_the_other_transport(mcp_daemon: Any) -> None:
    uid = _register_server()
    result = _edit("--header", "X=1")
    assert result.exit_code == 2
    assert "applies to a http server" in result.output
    assert _config_of(uid)["transport"].get("headers") is None


def test_mcp_edit_refuses_both_transports_and_bad_pairs(mcp_daemon: Any) -> None:
    _register_server()
    assert _edit("--stdio", "cat", "--http", "https://x.test").exit_code == 2
    assert _edit("--env", "NOVALUE").exit_code == 2
    assert _edit("--stdio", "").exit_code == 2


def test_mcp_edit_secret_looking_env_is_refused(mcp_daemon: Any) -> None:
    uid = _register_server()
    result = _edit("--env", "TOKEN=sk-live-123")
    assert result.exit_code != 0
    assert _config_of(uid)["transport"].get("env") in (None, {})


# ---------------------------------------------------------------------------
# coffer mcp rm
# ---------------------------------------------------------------------------


def test_mcp_rm_with_force(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "rm", "fs", "--force"])
    assert result.exit_code == 0, result.output
    assert "removed: MCP server fs" in result.output

    result2 = _runner.invoke(app, ["mcp", "show", "fs"])
    assert result2.exit_code == 4


def test_mcp_rm_not_found_with_force(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "rm", "ghost", "--force"])
    assert result.exit_code == 4


def test_mcp_rm_declined_confirmation_exits_1(mcp_daemon: Any) -> None:
    """Answering 'n' at the confirm prompt (no --force) aborts with exit 1
    and leaves the server registered."""
    _register_server()
    result = _runner.invoke(app, ["mcp", "rm", "fs"], input="n\n")
    assert result.exit_code == 1, result.output

    still = _runner.invoke(app, ["mcp", "show", "fs"])
    assert still.exit_code == 0, still.output


def test_mcp_group_offers_the_new_verbs_only() -> None:
    help_out = _runner.invoke(app, ["mcp", "--help"], env={"COLUMNS": "200"}).output
    for verb in ("list", "show", "add", "edit", "rm", "enable", "disable", "scope", "test", "cap"):
        assert f" {verb} " in help_out, verb
    for gone in ("remove", "refresh", "invocations", "tool", "resource", "prompt"):
        assert f" {gone} " not in help_out, gone


# ---------------------------------------------------------------------------
# coffer mcp test — refresh, then the health test. The upstream connection is
# faked at the route's seam, so the real route (and its health write) runs.
# ---------------------------------------------------------------------------


def _fake_upstream(monkeypatch: pytest.MonkeyPatch, *, answers: bool) -> None:
    from coffer.surfaces.http.mcp import server_test_routes

    class _Conn:
        def __init__(self, **_kw: Any) -> None:
            pass

        async def spawn_and_initialize(self) -> dict[str, Any]:
            if not answers:
                raise RuntimeError("connection refused")
            return {"tools": {}}

        async def close(self) -> None:
            return None

    monkeypatch.setattr(server_test_routes, "StdioUpstreamConnection", _Conn)


def _tool_names(result: Any) -> list[str]:
    assert result.exit_code == 0, result.output
    return [t["original_name"] for t in json.loads(result.output)["tools"]]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="test re-queries capabilities before reporting health"
)
def test_mcp_test_requeries_capabilities_then_reports_health(
    mcp_daemon: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_server()
    listed = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--type", "tool", "--json"])
    assert _tool_names(listed) == ["read_file"]

    # The upstream gains a tool; Coffer's cached view does not know yet.
    STUB["discovery"].tools.append("write_file")
    stale = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--type", "tool", "--json"])
    assert _tool_names(stale) == ["read_file"]

    _fake_upstream(monkeypatch, answers=True)
    result = _runner.invoke(app, ["mcp", "test", "fs"])
    assert result.exit_code == 0, result.output
    assert "2 tools" in result.output and "re-queried" in result.output
    assert "OK" in result.output

    fresh = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--type", "tool", "--json"])
    assert _tool_names(fresh) == ["read_file", "write_file"]

    # An unreachable upstream: the command exits non-zero and names the failure.
    STUB["discovery"].unreachable = True
    _fake_upstream(monkeypatch, answers=False)
    down = _runner.invoke(app, ["mcp", "test", "fs"])
    combined = down.output + (down.stderr or "")
    assert down.exit_code == 7, combined
    assert "FAIL" in combined and "connection refused" in combined


def test_mcp_test_not_found_exit_4(mcp_daemon: Any) -> None:
    """An unknown NAME fails at the lookup — the CLI names what the user typed."""
    result = _runner.invoke(app, ["mcp", "test", "ghost"])
    assert result.exit_code == 4, result.output
    assert "no mcp_server named 'ghost'" in (result.output + (result.stderr or ""))


# ---------------------------------------------------------------------------
# coffer mcp cap list / enable / disable
# ---------------------------------------------------------------------------


def _seed_pref(uid: str, capability_type: str, key: str) -> None:
    """Seed the preference row discovery would have written, so a toggle has a
    row to flip (the stub discovery writes none)."""
    from datetime import UTC, datetime

    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )
    from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo

    engine = create_async_engine_with_pragmas(os.environ["COFFER_DB_URL"])

    async def _seed() -> None:
        sm = session_maker(engine)
        resource = await SqlAlchemyResourceRepo(sm).find(uid)
        assert resource is not None
        now = datetime.now(tz=UTC)
        await MCPCapabilityPreferenceRepo(sm).insert(
            resource.id, capability_type, key, True, now, now
        )
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()


def test_mcp_cap_list_json_carries_every_type_with_its_ref(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert list(payload) == ["tools", "prompts", "resources"]
    assert [t["ref"] for t in payload["tools"]] == ["tool:read_file"]
    assert [r["ref"] for r in payload["resources"]] == ["resource:file:///tmp/x"]
    assert "\x1b[" not in result.output


def test_mcp_cap_list_table(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "list", "fs"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "tool:read_file" in result.output
    assert "resource:file:///tmp/x" in result.output


def test_mcp_cap_list_rejects_an_unknown_type(mcp_daemon: Any) -> None:
    _register_server()
    assert _runner.invoke(app, ["mcp", "cap", "list", "fs", "--type", "tools"]).exit_code == 2


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool with an over-long client-visible name is flagged"
)
def test_mcp_cap_list_flags_an_over_long_client_name(mcp_daemon: Any) -> None:
    # mcp__coffer__ (13) + "fs__" (4) + 53 = 70; 13 + 4 + 23 = 40.
    long_tool, short_tool = "t" * 53, "s" * 23
    STUB["discovery"].tools = [long_tool, short_tool]
    _register_server()

    result = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--json"])
    assert result.exit_code == 0, result.output
    tools = {t["original_name"]: t for t in json.loads(result.output)["tools"]}
    assert tools[long_tool]["client_name_length"] == 70
    assert tools[long_tool]["name_too_long"] is True
    assert "60" in tools[long_tool]["warning"]
    assert tools[short_tool]["client_name_length"] == 40
    assert tools[short_tool]["name_too_long"] is False
    assert "warning" not in tools[short_tool]
    # Flagging changes nothing: both stay enabled and listed.
    assert tools[long_tool]["enabled"] and tools[short_tool]["enabled"]

    table = _runner.invoke(app, ["mcp", "cap", "list", "fs"], env={"COLUMNS": "200"})
    assert table.exit_code == 0, table.output
    assert "70 !" in table.output
    assert "40 !" not in table.output
    assert "above 60" in " ".join(table.output.split())


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the command line toggles capabilities by typed ref"
)
def test_mcp_cap_toggles_capabilities_by_typed_ref(mcp_daemon: Any) -> None:
    STUB["discovery"].tools = ["read_file", "write_file"]
    STUB["discovery"].prompts = ["summarize"]
    uid = _register_server()
    for type_, key in (("tool", "read_file"), ("tool", "write_file"), ("prompt", "summarize")):
        _seed_pref(uid, type_, key)

    disabled = _runner.invoke(
        app, ["mcp", "cap", "disable", "fs", "tool:read_file", "prompt:summarize"]
    )
    assert disabled.exit_code == 0, disabled.output
    assert "disabled: fs tool:read_file" in disabled.output
    assert "disabled: fs prompt:summarize" in disabled.output

    listed = _runner.invoke(app, ["mcp", "cap", "list", "fs", "--type", "tool", "--json"])
    assert listed.exit_code == 0, listed.output
    payload = json.loads(listed.output)
    assert list(payload) == ["tools"]
    assert {t["original_name"]: t["enabled"] for t in payload["tools"]} == {
        "read_file": False,
        "write_file": True,
    }
    prompts = json.loads(_runner.invoke(app, ["mcp", "cap", "list", "fs", "--json"]).output)
    assert prompts["prompts"][0]["enabled"] is False

    # A ref naming nothing refuses the whole command, the valid ref beside it too.
    refused = _runner.invoke(
        app, ["mcp", "cap", "enable", "fs", "tool:read_file", "tool:no-such-tool"]
    )
    assert refused.exit_code != 0
    assert "tool:no-such-tool" in (refused.output + (refused.stderr or ""))
    after = json.loads(_runner.invoke(app, ["mcp", "cap", "list", "fs", "--json"]).output)
    assert {t["original_name"]: t["enabled"] for t in after["tools"]}["read_file"] is False

    enabled = _runner.invoke(app, ["mcp", "cap", "enable", "fs", "tool:read_file"])
    assert enabled.exit_code == 0, enabled.output


def test_mcp_cap_toggles_a_resource_uri_with_slashes(mcp_daemon: Any) -> None:
    """A resource key is a URI containing '/'; the ref splits on the FIRST
    colon only, and the key travels in the request body, not the URL path."""
    uid = _register_server()
    _seed_pref(uid, "resource", "file:///tmp/x")

    disabled = _runner.invoke(app, ["mcp", "cap", "disable", "fs", "resource:file:///tmp/x"])
    assert disabled.exit_code == 0, disabled.output
    enabled = _runner.invoke(app, ["mcp", "cap", "enable", "fs", "resource:file:///tmp/x"])
    assert enabled.exit_code == 0, enabled.output
    assert "enabled: fs resource:file:///tmp/x" in enabled.output


def test_mcp_cap_rejects_an_untyped_ref(mcp_daemon: Any) -> None:
    _register_server()
    result = _runner.invoke(app, ["mcp", "cap", "disable", "fs", "read_file"])
    assert result.exit_code == 2, result.output


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


def test_mcp_add_with_a_title(mcp_daemon: Any) -> None:
    result = _runner.invoke(app, ["mcp", "add", "fs", "--stdio", "cat", "--title", "Files"])
    assert result.exit_code == 0, result.output
    shown = json.loads(_runner.invoke(app, ["mcp", "show", "fs", "--json"]).output)
    assert shown["title"] == "Files"


# ---------------------------------------------------------------------------
# invocation rows, for the --json scenario (`coffer log mcp`)
# ---------------------------------------------------------------------------


def _seed_invocations(uid: str) -> None:
    """Seed two invocation rows (one ok, one error) under the server's uid."""
    from datetime import UTC, datetime

    from coffer.domain.mcp.capability import MCPInvocation
    from coffer.infrastructure.persistence.engine import (
        create_async_engine_with_pragmas,
        session_maker,
    )

    engine = create_async_engine_with_pragmas(os.environ["COFFER_DB_URL"])

    async def _seed() -> None:
        repo = MCPInvocationRepo(session_maker(engine))
        now = datetime.now(tz=UTC)
        for key, status, err in (("read_file", "ok", None), ("write_file", "error", "boom")):
            await repo.insert(
                MCPInvocation(
                    id=None,
                    timestamp=now,
                    resource_uid=uid,
                    capability_type="tool",
                    capability_key=key,
                    duration_ms=5,
                    status=status,
                    error_message=err,
                    session_id="s1",
                )
            )
        await engine.dispose()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()
