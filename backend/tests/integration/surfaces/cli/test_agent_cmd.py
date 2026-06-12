"""Integration tests for `coffer agent` CLI subcommands.

Covers TEST25-201: every verb (`list` / `add` / `show` / `edit` / `rm` /
`detect`) plus the `--json` switch on `list` and `show`.

The fixture builds a tiny in-process FastAPI app wired to a real
``AgentService`` over an in-tree SQLite DB, then monkeypatches
``_client.client_or_exit`` to return a ``starlette.testclient.TestClient``
wrapping that app. This mirrors the strategy used by
``test_resource_cmd.py`` and keeps the CLI verbs talking to the same HTTP
routes the desktop UI consumes — which is the spec scenario "CLI surface
mirrors REST operations".
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC
from datetime import datetime as dt

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import (
    get_agent_service,
    get_auto_detect_service,
)

_runner = CliRunner()
_TOKEN = "test-token-agent-cli"


@pytest.fixture
def agent_cli_daemon(tmp_path, monkeypatch):
    """In-process daemon with the agent router; patches `client_or_exit`."""
    monkeypatch.setenv("HOME", str(tmp_path))
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    engine = create_async_engine_with_pragmas(db_url)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_create_tables(engine))
    finally:
        loop.close()

    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    kinds = {"agent": make_agent_kind(on_delete=None)}
    resource_svc = ResourceService(kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    agent_svc = AgentService(resource_service=resource_svc, audit=audit)
    detect_svc = AutoDetectService(agent_service=agent_svc)

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_router)
    app.dependency_overrides[get_agent_service] = lambda: agent_svc
    app.dependency_overrides[get_auto_detect_service] = lambda: detect_svc

    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=8000,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )

    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, info))

    yield tmp_path

    set_active_token(None)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# agent list
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="004-agent-registry", scenario="CLI surface mirrors REST operations")
def test_agent_list_empty_json(agent_cli_daemon):
    """`agent list --json` prints an empty JSON list when no agents are registered."""
    result = _runner.invoke(cli_app, ["agent", "list", "--json"])
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert items == []


def test_agent_list_table_default(agent_cli_daemon):
    """`agent list` (no --json) renders the rich table without crashing."""
    # First register one so the table has a row to render.
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app,
        [
            "agent",
            "add",
            "codex",
            "--name",
            "cur",
            "--config-dir",
            str(config_dir),
        ],
    )
    result = _runner.invoke(cli_app, ["agent", "list"])
    assert result.exit_code == 0, result.output
    # Table title and the Config Dir column header must be present.
    assert "Agents" in result.output
    assert "Config Dir" in result.output
    assert "cur" in result.output


def test_agent_list_shows_registered_json(agent_cli_daemon):
    """`agent list --json` includes a previously-registered agent."""
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(config_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "list", "--json"])
    assert result.exit_code == 0
    items = json.loads(result.output)
    assert len(items) == 1
    assert items[0]["name"] == "cur"
    assert items[0]["type"] == "codex"
    assert items[0]["config_dir"] == str(config_dir)
    assert "skill_dir" not in items[0]


# ---------------------------------------------------------------------------
# agent add
# ---------------------------------------------------------------------------


def test_agent_add_success(agent_cli_daemon):
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    result = _runner.invoke(
        cli_app,
        [
            "agent",
            "add",
            "codex",
            "--name",
            "cur",
            "--config-dir",
            str(config_dir),
            "--description",
            "manual",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "registered" in result.output


def test_agent_add_without_name_uses_per_type_default(agent_cli_daemon):
    """FR-006: --name is optional; omitting it registers under the type's
    default name (codex -> codex, claude_code -> claude-code)."""
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    result = _runner.invoke(cli_app, ["agent", "add", "codex", "--config-dir", str(config_dir)])
    assert result.exit_code == 0, result.output
    assert "registered: agent:codex" in result.output
    # The agent is listed under the derived name.
    listed = _runner.invoke(cli_app, ["agent", "list", "--json"])
    names = [i["name"] for i in json.loads(listed.output)]
    assert "codex" in names


def test_agent_add_duplicate_fails(agent_cli_daemon):
    # Distinct config dirs so the collision is on the name, not the
    # one-agent-per-config-dir rule.
    first = agent_cli_daemon / "cfg1"
    second = agent_cli_daemon / "cfg2"
    first.mkdir()
    second.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(first)],
    )
    result = _runner.invoke(
        cli_app,
        [
            "agent",
            "add",
            "claude_code",
            "--name",
            "cur",
            "--config-dir",
            str(second),
        ],
    )
    # add() routes 4xx through _cli_client.check, which maps 409 →
    # ExitCode.CONFLICT (5). CODE25-018 — fix-validation.
    assert result.exit_code == 5, result.output


# ---------------------------------------------------------------------------
# agent show
# ---------------------------------------------------------------------------


def test_agent_show_existing_text(agent_cli_daemon):
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(config_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "show", "cur"])
    assert result.exit_code == 0, result.output
    assert "name: cur" in result.output
    assert "type: codex" in result.output
    assert f"config_dir: {config_dir}" in result.output


def test_agent_show_existing_json(agent_cli_daemon):
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(config_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "show", "cur", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["name"] == "cur"
    assert data["type"] == "codex"
    assert data["config_dir"] == str(config_dir)
    assert "skill_dir" not in data


def test_agent_show_not_found(agent_cli_daemon):
    result = _runner.invoke(cli_app, ["agent", "show", "ghost"])
    assert result.exit_code == 4, result.output


# ---------------------------------------------------------------------------
# agent edit
# ---------------------------------------------------------------------------


def test_agent_edit_config_dir(agent_cli_daemon):
    old = agent_cli_daemon / "cfg"
    new = agent_cli_daemon / "cfg2"
    old.mkdir()
    new.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(old)],
    )
    result = _runner.invoke(cli_app, ["agent", "edit", "cur", "--config-dir", str(new)])
    assert result.exit_code == 0, result.output
    assert "updated" in result.output
    # And the new config_dir was actually persisted.
    show = _runner.invoke(cli_app, ["agent", "show", "cur", "--json"])
    data = json.loads(show.output)
    assert data["config_dir"] == str(new)


def test_agent_edit_no_fields_exits_1(agent_cli_daemon):
    """`edit` with no flags is a no-op and exits non-zero with a clear message."""
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(config_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "edit", "cur"])
    assert result.exit_code == 1
    assert "nothing to update" in (result.output or result.stderr or "")


def test_agent_edit_description(agent_cli_daemon):
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(config_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "edit", "cur", "--description", "work box"])
    assert result.exit_code == 0, result.output
    show = _runner.invoke(cli_app, ["agent", "show", "cur", "--json"])
    assert json.loads(show.output)["description"] == "work box"


def test_agent_edit_not_found(agent_cli_daemon):
    result = _runner.invoke(cli_app, ["agent", "edit", "ghost", "--description", "x"])
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# agent rm
# ---------------------------------------------------------------------------


def test_agent_rm_force(agent_cli_daemon):
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(config_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "rm", "cur", "--force"])
    assert result.exit_code == 0, result.output
    assert "removed" in result.output
    # Subsequent show returns 404 -> exit 4.
    show = _runner.invoke(cli_app, ["agent", "show", "cur"])
    assert show.exit_code == 4


def test_agent_rm_not_found(agent_cli_daemon):
    result = _runner.invoke(cli_app, ["agent", "rm", "ghost", "--force"])
    assert result.exit_code == 4


def test_agent_rm_without_force_aborts(agent_cli_daemon):
    """Without --force the prompt aborts (empty stdin → typer.confirm returns False)."""
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "codex", "--name", "cur", "--config-dir", str(config_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "rm", "cur"], input="n\n")
    assert result.exit_code == 1
    # The agent must still exist.
    show = _runner.invoke(cli_app, ["agent", "show", "cur"])
    assert show.exit_code == 0


# ---------------------------------------------------------------------------
# agent detect
# ---------------------------------------------------------------------------


def test_agent_detect_no_markers(agent_cli_daemon):
    """`detect` against an empty HOME prints the no-new-agents message."""
    result = _runner.invoke(cli_app, ["agent", "detect"])
    assert result.exit_code == 0, result.output
    assert "no new agents detected" in result.output


def test_agent_detect_lists_candidates_marker_present(agent_cli_daemon):
    """`detect` with marker dirs lists each discovered candidate (read-only)."""
    (agent_cli_daemon / ".codex").mkdir()
    (agent_cli_daemon / ".claude").mkdir()
    result = _runner.invoke(cli_app, ["agent", "detect"])
    assert result.exit_code == 0, result.output
    assert "detected:" in result.output
    assert "codex" in result.output or "claude_code" in result.output
    # Discovery registers nothing — the registry stays empty.
    listed = _runner.invoke(cli_app, ["agent", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output) == []


# ---------------------------------------------------------------------------
# agent follow
# ---------------------------------------------------------------------------


def test_agent_follow_off_with_exclusions(agent_cli_daemon):
    """`follow --off --exclude x` PATCHes the policy; `show --json` reflects it."""
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    _runner.invoke(
        cli_app, ["agent", "add", "codex", "--name", "cur", "--config-dir", str(config_dir)]
    )

    r = _runner.invoke(
        cli_app, ["agent", "follow", "cur", "--off", "--exclude", "x", "--exclude", "y"]
    )
    assert r.exit_code == 0, r.output
    assert "follow_all_skills=off" in r.output

    show = _runner.invoke(cli_app, ["agent", "show", "cur", "--json"])
    data = json.loads(show.output)
    assert data["follow_all_skills"] is False
    assert data["skill_exclusions"] == ["x", "y"]

    # `--on` without --exclude leaves the exclusion list untouched.
    r = _runner.invoke(cli_app, ["agent", "follow", "cur", "--on"])
    assert r.exit_code == 0, r.output
    data = json.loads(_runner.invoke(cli_app, ["agent", "show", "cur", "--json"]).output)
    assert data["follow_all_skills"] is True
    assert data["skill_exclusions"] == ["x", "y"]


def test_agent_follow_not_found(agent_cli_daemon):
    r = _runner.invoke(cli_app, ["agent", "follow", "ghost", "--off"])
    assert r.exit_code == 4


# ---------------------------------------------------------------------------
# agent mcp entries / plugin (workspace, via the full app)
# ---------------------------------------------------------------------------

_SECRET_VALUE = "supersecret-value-31337"

_CODEX_CONFIG = f"""\
[mcp_servers.fetcher]
command = "uvx"
args = ["mcp-fetch"]

[mcp_servers.fetcher.env]
API_TOKEN = "{_SECRET_VALUE}"

[marketplaces.m1]
source_type = "git"
source = "https://example.com/m1.git"

[plugins."p1@m1"]
enabled = true

[plugins."p2@m1"]
enabled = false
"""


def _extract_json(output: str) -> str:
    """Skip alembic INFO log lines emitted by the in-process app lifespan."""
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


@pytest.fixture
def workspace_cli(tmp_path, monkeypatch):
    """Full in-process app (create_app) with a registered codex agent ``cx``.

    Same bootstrap as test_skill_cmd.py: the lifespan stays open for the whole
    test (CLI verbs use ``with c:`` which must not tear the app down), and the
    OS keychain is faked class-wide so adopt never touches the real keyring.
    """
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
    from coffer.surfaces.http.app import create_app

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59650")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59659")

    keyring: dict[str, str] = {}
    monkeypatch.setattr(KeyringAdapter, "get", lambda self, ref: keyring.get(ref))
    monkeypatch.setattr(
        KeyringAdapter, "set", lambda self, ref, value: keyring.__setitem__(ref, value)
    )
    monkeypatch.setattr(KeyringAdapter, "delete", lambda self, ref: keyring.pop(ref, None))

    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(_CODEX_CONFIG, encoding="utf-8")
    # Cache dir present for p1 only — p2 must list cache_present=False.
    (codex_dir / "plugins" / "cache" / "m1" / "p1").mkdir(parents=True)

    app = create_app()
    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1, pid=1, port=59650, token=_TOKEN, started_at=dt.now(tz=UTC), binary_path="/t"
    )
    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    fake_client.__enter__()

    class _PersistentClient:
        """Proxy so the CLI's ``with c:`` block does NOT close the app."""

        def __init__(self, inner: TestClient) -> None:
            self._inner = inner

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(self._inner, item)

    monkeypatch.setattr(
        _cli_client, "client_or_exit", lambda: (_PersistentClient(fake_client), info)
    )

    r = _runner.invoke(cli_app, ["agent", "add", "codex", "--name", "cx"])
    assert r.exit_code == 0, r.output

    yield tmp_path, keyring

    fake_client.__exit__(None, None, None)
    set_active_token(None)


def test_mcp_entries_list_json_and_table(workspace_cli):
    """`agent mcp entries --json` lists entries; secret VALUES never appear."""
    r = _runner.invoke(cli_app, ["agent", "mcp", "entries", "cx", "--json"])
    assert r.exit_code == 0, r.output
    body = json.loads(_extract_json(r.output))
    assert body["parse_errors"] == []
    by_name = {e["name"]: e for e in body["items"]}
    fetcher = by_name["fetcher"]
    assert fetcher["source"] == "config"
    assert fetcher["transport"] == "stdio"
    assert fetcher["secret_keys"] == ["API_TOKEN"]
    assert _SECRET_VALUE not in r.output

    r = _runner.invoke(cli_app, ["agent", "mcp", "entries", "cx"])
    assert r.exit_code == 0, r.output
    assert "fetcher" in r.output


def test_mcp_toggle_entry(workspace_cli):
    r = _runner.invoke(cli_app, ["agent", "mcp", "toggle-entry", "cx", "fetcher", "--disabled"])
    assert r.exit_code == 0, r.output
    body = json.loads(
        _extract_json(_runner.invoke(cli_app, ["agent", "mcp", "entries", "cx", "--json"]).output)
    )
    by_name = {e["name"]: e for e in body["items"]}
    assert by_name["fetcher"]["enabled"] is False


def test_mcp_remove_entry_force_and_prompt(workspace_cli):
    # Without --force the prompt aborts and the entry survives.
    r = _runner.invoke(cli_app, ["agent", "mcp", "remove-entry", "cx", "fetcher"], input="n\n")
    assert r.exit_code == 1
    body = json.loads(
        _extract_json(_runner.invoke(cli_app, ["agent", "mcp", "entries", "cx", "--json"]).output)
    )
    assert "fetcher" in [e["name"] for e in body["items"]]

    r = _runner.invoke(cli_app, ["agent", "mcp", "remove-entry", "cx", "fetcher", "--force"])
    assert r.exit_code == 0, r.output
    body = json.loads(
        _extract_json(_runner.invoke(cli_app, ["agent", "mcp", "entries", "cx", "--json"]).output)
    )
    assert "fetcher" not in [e["name"] for e in body["items"]]


def test_mcp_adopt_with_secret(workspace_cli):
    """`mcp adopt --secret KEY=REF` adopts the entry into a managed resource."""
    _tmp, keyring = workspace_cli
    # Without the secret mapping: exit 6 plus the --secret hint.
    r = _runner.invoke(cli_app, ["agent", "mcp", "adopt", "cx", "fetcher"])
    assert r.exit_code == 6, r.output
    assert "API_TOKEN" in r.output
    assert "--secret" in r.output

    ref = "mcp.fetcher.API_TOKEN"
    r = _runner.invoke(
        cli_app, ["agent", "mcp", "adopt", "cx", "fetcher", "--secret", f"API_TOKEN={ref}"]
    )
    assert r.exit_code == 0, r.output
    assert "adopted: mcp_server:fetcher" in r.output
    # The secret value landed in the (fake) keychain, keyed by the ref.
    assert keyring[ref] == _SECRET_VALUE


def test_mcp_adopt_bad_secret_syntax_exit2(workspace_cli):
    r = _runner.invoke(
        cli_app, ["agent", "mcp", "adopt", "cx", "fetcher", "--secret", "MISSING_EQUALS"]
    )
    assert r.exit_code == 2, r.output


def test_plugin_list_disable_uninstall(workspace_cli):
    r = _runner.invoke(cli_app, ["agent", "plugin", "list", "cx", "--json"])
    assert r.exit_code == 0, r.output
    body = json.loads(_extract_json(r.output))
    by_id = {p["id"]: p for p in body["items"]}
    assert by_id["p1@m1"]["enabled"] is True
    assert by_id["p1@m1"]["cache_present"] is True
    assert by_id["p2@m1"]["cache_present"] is False
    assert [m["name"] for m in body["marketplaces"]] == ["m1"]

    # Table path renders without crashing and shows the marketplace line.
    r = _runner.invoke(cli_app, ["agent", "plugin", "list", "cx"])
    assert r.exit_code == 0, r.output
    assert "p1@m1" in r.output
    assert "marketplace: m1" in r.output

    r = _runner.invoke(cli_app, ["agent", "plugin", "disable", "cx", "p1@m1"])
    assert r.exit_code == 0, r.output
    body = json.loads(
        _extract_json(_runner.invoke(cli_app, ["agent", "plugin", "list", "cx", "--json"]).output)
    )
    assert {p["id"]: p for p in body["items"]}["p1@m1"]["enabled"] is False

    # Uninstall without --force prompts and aborts.
    r = _runner.invoke(cli_app, ["agent", "plugin", "uninstall", "cx", "p2@m1"], input="n\n")
    assert r.exit_code == 1
    r = _runner.invoke(cli_app, ["agent", "plugin", "uninstall", "cx", "p2@m1", "--force"])
    assert r.exit_code == 0, r.output
    body = json.loads(
        _extract_json(_runner.invoke(cli_app, ["agent", "plugin", "list", "cx", "--json"]).output)
    )
    assert "p2@m1" not in [p["id"] for p in body["items"]]


def test_plugin_enable(workspace_cli):
    r = _runner.invoke(cli_app, ["agent", "plugin", "enable", "cx", "p2@m1"])
    assert r.exit_code == 0, r.output
    body = json.loads(
        _extract_json(_runner.invoke(cli_app, ["agent", "plugin", "list", "cx", "--json"]).output)
    )
    assert {p["id"]: p for p in body["items"]}["p2@m1"]["enabled"] is True
