"""Integration tests for `coffer agent` CLI subcommands.

Covers every verb (`list` / `add` / `show` / `edit` / `rm` / `enable` /
`disable`) plus the `--json` switch on `list` and `show`, the candidate rows
`coffer scan` prints, and (through the full app) plugins and direct MCP entries.

The fixture builds a tiny in-process FastAPI app wired to a real
``AgentService`` over an in-tree SQLite DB, then monkeypatches
``_client.client_or_exit`` to return a ``starlette.testclient.TestClient``
wrapping that app. This mirrors the strategy used by
``conftest.py``'s ``in_proc_daemon`` and keeps the CLI verbs talking to the same HTTP
routes the desktop UI consumes — which is the spec scenario "CLI surface
mirrors REST operations".

"Tiny" now means two routers, not one. Every ``coffer agent`` verb takes the
agent's TYPE (its name) and resolves it to the uid the routes address
(ADR resource-identity-is-an-immutable-uid), and that resolution is
``GET /resources?kind=agent&name=`` — the framework's shared route, on a
different router from ``/agents``. An app serving only ``agent_router`` would
fail every name-taking command before it ever reached an agent route, and it
would fail with a 404 that *looks* like "no such agent", which is the sort of
green-for-the-wrong-reason a fixture should never be able to produce. So the
app mounts ``resource_router`` too, over the same ``ResourceService`` the
``AgentService`` is built on — the same shape ``test_provider_cmd.py`` uses.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC
from datetime import datetime as dt

import pytest
import typer
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
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
from coffer.infrastructure.platform import HostPlatform
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.agent_dependencies import (
    get_agent_service,
    get_auto_detect_service,
)
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router
from tests.support.facets import agent_catalog, installed

_runner = CliRunner()
_TOKEN = "test-token-agent-cli"


@pytest.fixture
def agent_cli_daemon(tmp_path, monkeypatch):
    """In-process daemon with the agent + resource routers; patches `client_or_exit`."""
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
    agent_svc = AgentService(platform=HostPlatform(), resource_service=resource_svc, audit=audit)
    detect_svc = AutoDetectService(
        agent_service=agent_svc,
        catalog=agent_catalog({AgentType.CODEX: installed("0.155.1")}),
    )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_router)
    # Name → uid resolution lives on the framework's resource router, and every
    # `coffer agent` verb that takes a name goes through it first, so it is as
    # load-bearing here as `/agents` itself. The SAME ResourceService instance
    # the AgentService was built on: two would each have their own DB session
    # and the resolver would look for an agent in a registry nothing registered
    # into.
    app.include_router(resource_router)
    app.include_router(audit_router)
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_agent_service] = lambda: agent_svc
    app.dependency_overrides[get_auto_detect_service] = lambda: detect_svc
    app.dependency_overrides[get_resource_service] = lambda: resource_svc

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


def _listed(**kw) -> list[dict]:
    result = _runner.invoke(cli_app, ["agent", "list", "--json"], **kw)
    assert result.exit_code == 0, result.output
    return list(json.loads(result.output)["resources"])


def _audit_events(uid: str) -> list[str]:
    client, _info = _cli_client.client_or_exit()
    r = client.get("/audit", params={"resource_uid": uid})
    assert r.status_code == 200, r.text
    return [e["event_type"] for e in r.json()["entries"]]


def _show_json(ref: str) -> dict:
    result = _runner.invoke(cli_app, ["agent", "show", ref, "--json"])
    assert result.exit_code == 0, result.output
    return dict(json.loads(result.output))


def test_agent_list_empty_json(agent_cli_daemon):
    """`agent list --json` prints no rows when no agents are registered."""
    assert _listed() == []


def test_agent_list_table_default(agent_cli_daemon):
    """`agent list` (no --json) renders the rich table: the type's name, the
    product's display name, the enabled flag and the config dir."""
    _add_codex(agent_cli_daemon)
    result = _runner.invoke(cli_app, ["agent", "list"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "Agents" in result.output
    for header in ("Type", "Agent", "Enabled", "Config Dir"):
        assert header in result.output
    assert "codex" in result.output
    assert "OpenAI Codex" in result.output


@pytest.mark.acceptance(spec="agent-registry", scenario="agent reads print JSON with --json")
def test_agent_list_shows_registered_json(agent_cli_daemon):
    """`agent list --json` carries the agent's name, display name, type and
    config directory — and no title or description, which an agent has none of."""
    config_dir = _add_codex(agent_cli_daemon)
    items = _listed()
    assert len(items) == 1
    assert items[0]["name"] == "codex"
    assert items[0]["display_name"] == "OpenAI Codex"
    assert items[0]["type"] == "codex"
    assert items[0]["config_dir"] == str(config_dir)
    assert "title" not in items[0]
    assert "description" not in items[0]
    assert "skill_dir" not in items[0]


# ---------------------------------------------------------------------------
# agent add
# ---------------------------------------------------------------------------


def test_agent_add_success(agent_cli_daemon):
    config_dir = agent_cli_daemon / "cfg"
    config_dir.mkdir()
    result = _runner.invoke(cli_app, ["agent", "add", "codex", "--config-dir", str(config_dir)])
    assert result.exit_code == 0, result.output
    assert "registered: agent codex" in result.output


@pytest.mark.acceptance(
    spec="agent-registry", scenario="register an agent without an explicit name"
)
def test_agent_add_registers_by_type_only(agent_cli_daemon):
    """`coffer agent add claude-code` — the type alone — registers the agent
    under the type's name at its standard config directory, audited as
    `resource_created`. There is no `--name` to give."""
    standard = agent_cli_daemon / ".claude"
    standard.mkdir()
    result = _runner.invoke(cli_app, ["agent", "add", "claude-code"])
    assert result.exit_code == 0, result.output
    assert "registered: agent claude-code" in result.output
    [agent] = _listed()
    assert (agent["name"], agent["type"], agent["config_dir"]) == (
        "claude-code",
        "claude_code",
        str(standard),
    )
    assert "resource_created" in _audit_events(agent["uid"])

    named = _runner.invoke(cli_app, ["agent", "add", "codex", "--name", "cur"])
    assert named.exit_code == 2, named.output


@pytest.mark.acceptance(spec="agent-registry", scenario="reject duplicate agent name")
def test_agent_add_duplicate_fails(agent_cli_daemon):
    """A second agent of a registered type — even on another directory — is
    refused: its name would be the type's, which the first one holds."""
    _add_codex(agent_cli_daemon)
    uid = _listed()[0]["uid"]
    other = agent_cli_daemon / "cfg2"
    other.mkdir()
    result = _runner.invoke(cli_app, ["agent", "add", "codex", "--config-dir", str(other)])
    # 409 maps to ExitCode.CONFLICT (5).
    assert result.exit_code == 5, result.output
    assert [(a["name"], a["uid"]) for a in _listed()] == [("codex", uid)]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="adopt a discovered agent from the command line"
)
def test_adopt_a_discovered_agent_from_the_command_line(agent_cli_daemon):
    codex_home = agent_cli_daemon / ".codex"
    codex_home.mkdir()

    scanned = _runner.invoke(cli_app, ["scan", "--json"])
    assert scanned.exit_code == 0, scanned.output
    rows = [r for r in json.loads(scanned.output)["rows"] if r["kind"] == "agent"]
    [row] = [r for r in rows if r["ref"] == "codex"]
    assert "coffer agent add codex" in row["detail"]
    assert "--config-dir" not in row["detail"]
    assert _listed() == []

    added = _runner.invoke(cli_app, ["agent", "add", "codex"])
    assert added.exit_code == 0, added.output
    [agent] = _listed()
    assert (agent["name"], agent["config_dir"]) == ("codex", str(codex_home))
    assert "resource_created" in _audit_events(agent["uid"])

    for verb in ("adopt", "discard"):
        group = typer.main.get_command(cli_app).commands[verb]  # type: ignore[attr-defined]
        assert "agent" not in group.commands  # type: ignore[attr-defined]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="the command line prints an agent's install prompt"
)
def test_the_command_line_prints_an_agents_install_prompt(agent_cli_daemon):
    # Claude Code's program is not found here (the catalogue installs Codex only).
    printed = _runner.invoke(cli_app, ["agent", "prompt", "claude-code"])
    assert printed.exit_code == 0, printed.output
    assert printed.output.startswith("Please install Claude Code on this machine")
    assert "`claude --version`" in printed.output

    as_json = _runner.invoke(cli_app, ["agent", "prompt", "claude_code", "--json"])
    assert as_json.exit_code == 0, as_json.output
    body = json.loads(as_json.output)
    assert body["name"] == "claude-code"
    assert body["handoff"]["prompt"] == printed.output.rstrip("\n")

    # An installed program has nothing to hand off.
    found = _runner.invoke(cli_app, ["agent", "prompt", "codex"])
    assert found.exit_code == 5
    assert "nothing to hand off" in found.output


# ---------------------------------------------------------------------------
# agent show
# ---------------------------------------------------------------------------


def test_agent_show_existing_text(agent_cli_daemon):
    config_dir = _add_codex(agent_cli_daemon)
    result = _runner.invoke(cli_app, ["agent", "show", "codex"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    # The product's display name heads the record, then the name typed, the
    # uid everything else addresses, the type and the directory.
    assert lines[0] == "OpenAI Codex"
    assert "name: codex" in result.output
    assert "type: codex" in result.output
    assert f"config_dir: {config_dir}" in result.output
    keys = [line.split(":", 1)[0] for line in lines if ":" in line]
    assert keys[:4] == ["name", "uid", "type", "config_dir"], result.output
    assert "title" not in keys
    assert "description" not in keys


@pytest.mark.acceptance(spec="agent-registry", scenario="agent reads print JSON with --json")
def test_agent_show_existing_json(agent_cli_daemon):
    config_dir = _add_codex(agent_cli_daemon)
    data = _show_json("codex")
    assert data["name"] == "codex"
    assert data["display_name"] == "OpenAI Codex"
    assert data["type"] == "codex"
    assert data["config_dir"] == str(config_dir)
    assert "title" not in data
    assert "skill_dir" not in data
    assert data["uid"]
    # The derived connection is always present. This app does not serve the
    # connection route, so it is unknown (null).
    assert "coffer_connection" in data
    assert data["coffer_connection"] is None


@pytest.mark.acceptance(spec="agent-registry", scenario="address an agent by its type")
def test_agent_show_takes_the_type_either_spelling_or_the_uid(agent_cli_daemon):
    (agent_cli_daemon / ".claude").mkdir()
    assert _runner.invoke(cli_app, ["agent", "add", "claude_code"]).exit_code == 0
    uid = _listed()[0]["uid"]
    for ref in ("claude-code", "claude_code", uid):
        data = _show_json(ref)
        assert (data["name"], data["uid"]) == ("claude-code", uid), ref
    missing = _runner.invoke(cli_app, ["agent", "show", "codex"])
    assert missing.exit_code == 4, missing.output


def test_agent_show_prints_the_uid_the_daemon_reports(agent_cli_daemon):
    """The uid `show` prints is the one the resolution route answers with —
    the type the user typed and the uid every route takes denote one agent."""
    _add_codex(agent_cli_daemon)
    shown = _runner.invoke(cli_app, ["agent", "show", "codex"])
    assert shown.exit_code == 0, shown.output
    printed = [
        line.split(": ", 1)[1] for line in shown.output.splitlines() if line.startswith("uid: ")
    ]
    client, _info = _cli_client.client_or_exit()
    r = client.get("/resources", params={"kind": "agent", "name": "codex"})
    assert r.status_code == 200, r.text
    assert printed == [res["uid"] for res in r.json()["resources"]]


def test_agent_show_not_found(agent_cli_daemon):
    """An unheld ref fails at resolution, before any agent route is reached."""
    result = _runner.invoke(cli_app, ["agent", "show", "ghost"])
    assert result.exit_code == 4, result.output
    assert "no agent named 'ghost'" in (result.output + (result.stderr or ""))


# ---------------------------------------------------------------------------
# agent edit
# ---------------------------------------------------------------------------


def test_agent_edit_config_dir(agent_cli_daemon):
    _add_codex(agent_cli_daemon)
    new = agent_cli_daemon / "cfg2"
    new.mkdir()
    result = _runner.invoke(cli_app, ["agent", "edit", "codex", "--config-dir", str(new)])
    assert result.exit_code == 0, result.output
    assert "updated: agent codex" in result.output
    assert _show_json("codex")["config_dir"] == str(new)


@pytest.mark.acceptance(
    spec="agent-registry", scenario="use a different config directory from the command line"
)
def test_use_a_different_config_directory_from_the_command_line(agent_cli_daemon):
    standard = agent_cli_daemon / ".claude"
    standard.mkdir()
    assert _runner.invoke(cli_app, ["agent", "add", "claude-code"]).exit_code == 0
    before = _show_json("claude-code")
    assert before["config_dir"] == str(standard)
    other = agent_cli_daemon / "elsewhere"
    other.mkdir()

    result = _runner.invoke(cli_app, ["agent", "edit", "claude-code", "--config-dir", str(other)])
    assert result.exit_code == 0, result.output

    after = _show_json("claude-code")
    assert (after["config_dir"], after["uid"], after["name"]) == (
        str(other),
        before["uid"],
        "claude-code",
    )
    group = typer.main.get_command(cli_app).commands["agent"]  # type: ignore[attr-defined]
    options = {o for p in group.commands["edit"].params for o in p.opts}
    assert not {"--name", "--title", "--description"} & options, options


def test_agent_edit_no_fields_exits_2(agent_cli_daemon):
    """`edit` with no flags is a no-op and exits non-zero with a clear message."""
    _add_codex(agent_cli_daemon)
    result = _runner.invoke(cli_app, ["agent", "edit", "codex"])
    assert result.exit_code == 2
    assert "nothing to change" in (result.output + (result.stderr or ""))


def test_agent_edit_has_no_description(agent_cli_daemon):
    """An agent carries no description, so `--description` is an unknown option."""
    _add_codex(agent_cli_daemon)
    result = _runner.invoke(cli_app, ["agent", "edit", "codex", "--description", "work box"])
    assert result.exit_code == 2, result.output
    assert "description" not in _show_json("codex")


def test_agent_edit_not_found(agent_cli_daemon):
    """Resolution runs before the PATCH, so an unheld ref never reaches it."""
    result = _runner.invoke(cli_app, ["agent", "edit", "ghost", "--model", "x"])
    assert result.exit_code == 4
    assert "no agent named 'ghost'" in (result.output + (result.stderr or ""))


# ---------------------------------------------------------------------------
# agent rm
# ---------------------------------------------------------------------------


def test_agent_rm_force(agent_cli_daemon):
    _add_codex(agent_cli_daemon)
    result = _runner.invoke(cli_app, ["agent", "rm", "codex", "--force"])
    assert result.exit_code == 0, result.output
    assert "removed: agent codex" in result.output
    show = _runner.invoke(cli_app, ["agent", "show", "codex"])
    assert show.exit_code == 4
    assert "no agent named 'codex'" in (show.output + (show.stderr or ""))


def test_agent_rm_not_found(agent_cli_daemon):
    """Resolution runs before the DELETE, so an unheld ref never reaches it."""
    result = _runner.invoke(cli_app, ["agent", "rm", "ghost", "--force"])
    assert result.exit_code == 4
    assert "no agent named 'ghost'" in (result.output + (result.stderr or ""))


def test_agent_rm_without_force_aborts(agent_cli_daemon):
    """Without --force the prompt aborts (empty stdin → typer.confirm returns False)."""
    _add_codex(agent_cli_daemon)
    result = _runner.invoke(cli_app, ["agent", "rm", "codex"], input="n\n")
    assert result.exit_code == 1
    assert "Really remove agent codex?" in result.output
    show = _runner.invoke(cli_app, ["agent", "show", "codex"])
    assert show.exit_code == 0


# ---------------------------------------------------------------------------
# title and rename refused, enable/disable, and the verb set against REST
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry", scenario="give an agent a title from the command line"
)
def test_give_an_agent_a_title_from_the_command_line(agent_cli_daemon):
    (agent_cli_daemon / ".claude").mkdir()
    assert _runner.invoke(cli_app, ["agent", "add", "claude-code"]).exit_code == 0
    uid = _show_json("claude-code")["uid"]

    result = _runner.invoke(
        cli_app, ["agent", "edit", "claude-code", "--title", "Work laptop Claude"]
    )
    # typer's exit code for an option the command does not have.
    assert result.exit_code == 2, result.output

    client, _info = _cli_client.client_or_exit()
    r = client.patch(f"/resources/{uid}", json={"title": "Work laptop Claude"})
    assert r.status_code == 422, r.text

    shown = _runner.invoke(cli_app, ["agent", "show", "claude-code"])
    assert shown.exit_code == 0, shown.output
    assert "Work laptop Claude" not in shown.output
    data = _show_json("claude-code")
    assert (data["name"], data["uid"]) == ("claude-code", uid)
    assert "title" not in data
    assert client.get(f"/resources/{uid}").json()["title"] is None


def test_agent_edit_has_no_rename(agent_cli_daemon):
    """The name is the type's: `--name` is not an option, and the kind-agnostic
    route refuses a rename with NAME_IMMUTABLE."""
    _add_codex(agent_cli_daemon)
    result = _runner.invoke(cli_app, ["agent", "edit", "codex", "--name", "box"])
    assert result.exit_code == 2, result.output
    uid = _listed()[0]["uid"]
    client, _info = _cli_client.client_or_exit()
    r = client.patch(f"/resources/{uid}", json={"name": "box"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "NAME_IMMUTABLE"
    assert [a["name"] for a in _listed()] == ["codex"]


@pytest.mark.acceptance(
    spec="agent-registry", scenario="switch an agent off and on from the command line"
)
def test_switch_an_agent_off_and_on_from_the_command_line(agent_cli_daemon):
    _add_codex(agent_cli_daemon)
    off = _runner.invoke(cli_app, ["agent", "disable", "codex"])
    assert off.exit_code == 0, off.output
    assert _listed()[0]["enabled"] is False
    on = _runner.invoke(cli_app, ["agent", "enable", "codex"])
    assert on.exit_code == 0, on.output
    agent = _listed()[0]
    assert agent["enabled"] is True
    events = _audit_events(agent["uid"])
    assert events.index("resource_enabled") < events.index("resource_disabled"), events


@pytest.mark.acceptance(spec="agent-registry", scenario="CLI surface mirrors REST operations")
def test_every_agent_verb_mirrors_its_rest_route(agent_cli_daemon):
    client, _info = _cli_client.client_or_exit()
    config_dir = _add_codex(agent_cli_daemon)
    uid = _listed()[0]["uid"]
    assert client.get(f"/agents/{uid}").json()["config_dir"] == str(config_dir)

    new_dir = agent_cli_daemon / "moved"
    new_dir.mkdir()
    edited = _runner.invoke(cli_app, ["agent", "edit", "codex", "--config-dir", str(new_dir)])
    assert edited.exit_code == 0, edited.output
    assert client.get(f"/agents/{uid}").json()["config_dir"] == str(new_dir)

    shown = _show_json(uid)
    assert shown["config_dir"] == client.get(f"/agents/{uid}").json()["config_dir"]

    assert _runner.invoke(cli_app, ["agent", "disable", "codex"]).exit_code == 0
    assert client.get(f"/resources/{uid}").json()["enabled"] is False
    assert _runner.invoke(cli_app, ["agent", "enable", "codex"]).exit_code == 0
    assert client.get(f"/resources/{uid}").json()["enabled"] is True

    scanned = _runner.invoke(cli_app, ["scan", "--json"])
    assert scanned.exit_code == 0, scanned.output
    assert "rows" in json.loads(scanned.output)

    assert _runner.invoke(cli_app, ["agent", "rm", "codex", "--yes"]).exit_code == 0
    assert client.get("/agents").json()["items"] == []
    assert _listed() == []


@pytest.mark.acceptance(
    spec="agent-registry", scenario="list discovery candidates from the command line"
)
def test_scan_lists_the_candidate_and_registers_nothing(agent_cli_daemon):
    (agent_cli_daemon / ".codex").mkdir()

    result = _runner.invoke(cli_app, ["scan", "--json"])

    assert result.exit_code == 0, result.output
    rows = {r["ref"]: r for r in json.loads(result.output)["rows"] if r["kind"] == "agent"}
    assert rows["codex"]["config_dir"] == str(agent_cli_daemon / ".codex")
    assert (rows["codex"]["state"], rows["codex"]["version"]) == ("installed_active", "0.155.1")
    assert "coffer agent add codex" in rows["codex"]["detail"]
    assert _listed() == []


def test_agent_group_offers_the_new_commands_only():
    # Read off the command tree, not the rendered --help: the help layout is
    # the renderer's, and it changes between typer/rich releases.
    group = typer.main.get_command(cli_app).commands["agent"]  # type: ignore[attr-defined]
    assert set(group.commands) == {
        "list", "show", "add", "edit", "rm", "enable", "disable",
        "connect", "disconnect", "transcript", "models", "config", "plugin", "hooks", "prompt",
    }  # fmt: skip


# ---------------------------------------------------------------------------
# scanned MCP entries and plugins (workspace, via the full app)
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
    """Full in-process app (create_app) with a registered codex agent.

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

    r = _runner.invoke(cli_app, ["agent", "add", "codex"])
    assert r.exit_code == 0, r.output

    yield tmp_path, keyring

    fake_client.__exit__(None, None, None)
    set_active_token(None)


def test_scan_lists_the_agents_mcp_entries_without_secret_values(workspace_cli):
    """`scan --agent codex --json` carries the direct entry; secret VALUES never appear."""
    r = _runner.invoke(cli_app, ["scan", "--agent", "codex", "--json"])
    assert r.exit_code == 0, r.output
    rows = {row["ref"]: row for row in json.loads(_extract_json(r.output))["rows"]}
    assert rows["codex:fetcher"]["kind"] == "mcp"
    assert rows["codex:fetcher"]["source"] == "config"
    assert _SECRET_VALUE not in r.output


def test_scan_ref_prints_an_mcp_entry_without_secret_values(workspace_cli):
    """`scan --ref <agent>:<entry>` reads one entry in full: file, command, key names."""
    tmp_path, _keyring = workspace_cli
    r = _runner.invoke(cli_app, ["scan", "--ref", "codex:fetcher", "--json"])
    assert r.exit_code == 0, r.output
    body = json.loads(_extract_json(r.output))
    assert body["path"] == str(tmp_path / ".codex" / "config.toml")
    assert body["command"] == "uvx"
    assert body["args"] == ["mcp-fetch"]
    assert body["secret_keys"] == ["API_TOKEN"]
    assert _SECRET_VALUE not in r.output

    r = _runner.invoke(cli_app, ["scan", "--ref", "codex:fetcher"])
    assert r.exit_code == 0, r.output
    assert f"file: {tmp_path / '.codex' / 'config.toml'}" in r.output
    assert "command: uvx mcp-fetch" in r.output
    assert "env API_TOKEN: (secret)" in r.output
    assert _SECRET_VALUE not in r.output

    r = _runner.invoke(cli_app, ["scan", "--ref", "codex:missing"])
    assert r.exit_code == 4, r.output


def test_discard_mcp_entry_asks_first(workspace_cli):
    # Declining the prompt leaves the entry where it is.
    r = _runner.invoke(cli_app, ["discard", "mcp", "codex:fetcher"], input="n\n")
    assert r.exit_code == 1
    scanned = _runner.invoke(cli_app, ["scan", "--agent", "codex", "--json"]).output
    assert "codex:fetcher" in scanned

    r = _runner.invoke(cli_app, ["discard", "mcp", "codex:fetcher", "--yes"])
    assert r.exit_code == 0, r.output
    scanned = _runner.invoke(cli_app, ["scan", "--agent", "codex", "--json"]).output
    assert "codex:fetcher" not in scanned


def test_adopt_mcp_entry_with_secret(workspace_cli):
    """`adopt mcp --secret KEY=REF` adopts the entry into a managed resource."""
    _tmp, _keyring = workspace_cli
    # Without the secret mapping: exit 6 plus the --secret hint.
    r = _runner.invoke(cli_app, ["adopt", "mcp", "codex:fetcher"])
    assert r.exit_code == 6, r.output
    assert "API_TOKEN" in r.output
    assert "--secret" in r.output

    ref = "mcp.fetcher.API_TOKEN"
    r = _runner.invoke(cli_app, ["adopt", "mcp", "codex:fetcher", "--secret", f"API_TOKEN={ref}"])
    assert r.exit_code == 0, r.output
    # The secret value landed in the encrypted credential store, keyed by the
    # ref. The CLI only confirms presence (no command prints a value), so the
    # value itself is read from the daemon's own store.
    r = _runner.invoke(cli_app, ["credentials", "get", ref])
    assert r.exit_code == 0, r.output
    assert _SECRET_VALUE not in r.output
    from coffer.surfaces.http.credential_composition import get_credential_store

    assert get_credential_store().get(ref) == _SECRET_VALUE


def test_plugin_list_enable_disable(workspace_cli):
    """`agent plugin list` shows both plugins; enable/disable flip the config."""
    r = _runner.invoke(cli_app, ["agent", "plugin", "list", "codex", "--json"])
    assert r.exit_code == 0, r.output
    body = json.loads(_extract_json(r.output))
    by_id = {p["id"]: p for p in body["items"]}
    assert by_id["p1@m1"]["enabled"] is True
    assert by_id["p2@m1"]["enabled"] is False

    r = _runner.invoke(cli_app, ["agent", "plugin", "disable", "codex", "p1@m1"])
    assert r.exit_code == 0, r.output
    assert "disabled: plugin p1@m1" in r.output

    r = _runner.invoke(cli_app, ["agent", "plugin", "enable", "codex", "p2@m1"])
    assert r.exit_code == 0, r.output
    assert "enabled: plugin p2@m1" in r.output

    body = json.loads(
        _extract_json(
            _runner.invoke(cli_app, ["agent", "plugin", "list", "codex", "--json"]).output
        )
    )
    by_id = {p["id"]: p for p in body["items"]}
    assert by_id["p1@m1"]["enabled"] is False
    assert by_id["p2@m1"]["enabled"] is True


def test_plugin_show_prints_contents_and_json(workspace_cli):
    """`agent plugin show` reads the detail route: metadata and contents as
    text, the route's body unchanged with --json, exit 4 for an unknown id."""
    tmp_path, _keyring = workspace_cli
    pkg = tmp_path / ".codex" / "plugins" / "cache" / "m1" / "p1" / "0.3.0"
    (pkg / ".codex-plugin").mkdir(parents=True)
    (pkg / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"version": "0.3.0", "author": "Ada"}), encoding="utf-8"
    )
    (pkg / "commands").mkdir()
    (pkg / "commands" / "fix.md").write_text("---\ndescription: Fix it\n---\n", encoding="utf-8")
    (pkg / ".mcp.json").write_text(json.dumps({"mcpServers": {"srv": {}}}), encoding="utf-8")

    r = _runner.invoke(cli_app, ["agent", "plugin", "show", "codex", "p1@m1"])
    assert r.exit_code == 0, r.output
    assert "p1@m1  enabled" in r.output
    assert "author: Ada" in r.output
    assert "marketplace: m1 (https://example.com/m1.git)" in r.output
    assert f"installed at: {pkg}" in r.output
    assert "command: fix — Fix it" in r.output
    assert "mcp server: srv" in r.output

    r = _runner.invoke(cli_app, ["agent", "plugin", "show", "codex", "p1@m1", "--json"])
    assert r.exit_code == 0, r.output
    body = json.loads(_extract_json(r.output))
    assert body["commands"] == [{"name": "fix", "description": "Fix it"}]
    assert body["install_path"] == str(pkg)

    r = _runner.invoke(cli_app, ["agent", "plugin", "show", "codex", "ghost@m1"])
    assert r.exit_code == 4, r.output
    assert "plugin not found" in r.output


def test_plugin_enable_unknown_id_exit4(workspace_cli):
    r = _runner.invoke(cli_app, ["agent", "plugin", "enable", "codex", "ghost@m1"])
    assert r.exit_code == 4, r.output
    assert "plugin not found" in r.output


def test_plugin_rm_force_and_prompt(workspace_cli):
    tmp_path, _keyring = workspace_cli
    cache_dir = tmp_path / ".codex" / "plugins" / "cache" / "m1" / "p1"

    # Without --force the prompt aborts and the plugin survives.
    r = _runner.invoke(cli_app, ["agent", "plugin", "rm", "codex", "p1@m1"], input="n\n")
    assert r.exit_code == 1
    assert cache_dir.is_dir()

    r = _runner.invoke(cli_app, ["agent", "plugin", "rm", "codex", "p1@m1", "--force"])
    assert r.exit_code == 0, r.output
    assert "removed: plugin p1@m1" in r.output
    body = json.loads(
        _extract_json(
            _runner.invoke(cli_app, ["agent", "plugin", "list", "codex", "--json"]).output
        )
    )
    assert [p["id"] for p in body["items"]] == ["p2@m1"]
    assert not cache_dir.exists()


# ---------------------------------------------------------------------------
# agent edit — the model binding (spec provider-switching "Take projected
# model keys from the agent's binding")
#
# PATCH /agents/{uid} has carried `model` / `fast_model` / `wire_api` since the
# per-agent binding landed, and the projector reads exactly those fields
# (`application/provider/projector.py`). Until these options existed a
# terminal-only user could activate a connection and never bind a model to it,
# so the agent kept answering on its own default and nothing said why.
# ---------------------------------------------------------------------------


def _add_codex(agent_cli_daemon):
    config_dir = agent_cli_daemon / "cfg-codex"
    config_dir.mkdir(exist_ok=True)
    added = _runner.invoke(cli_app, ["agent", "add", "codex", "--config-dir", str(config_dir)])
    assert added.exit_code == 0, added.output
    return config_dir


def test_agent_edit_binds_a_model(agent_cli_daemon):
    _add_codex(agent_cli_daemon)
    result = _runner.invoke(cli_app, ["agent", "edit", "codex", "--model", "gpt-5-codex"])
    assert result.exit_code == 0, result.output
    shown = json.loads(_runner.invoke(cli_app, ["agent", "show", "codex", "--json"]).output)
    assert shown["model"] == "gpt-5-codex"


@pytest.mark.acceptance(
    spec="agent-registry", scenario="bind a model to an agent from the command line"
)
def test_agent_edit_binds_effort_and_tiers_and_can_clear_them(agent_cli_daemon):
    """The route distinguishes "absent" from "explicitly null" via
    ``model_fields_set``; the CLI needs a way to say the second one, otherwise
    an effort or a tier pin can be set and never taken off."""
    _add_codex(agent_cli_daemon)
    bound = _runner.invoke(
        cli_app,
        [
            "agent", "edit", "codex", "--model", "big", "--effort", "high",
            "--tier", "haiku=small", "--tier", "opus=big",
        ],
    )  # fmt: skip
    assert bound.exit_code == 0, bound.output
    shown = json.loads(_runner.invoke(cli_app, ["agent", "show", "codex", "--json"]).output)
    assert (shown["model"], shown["effort"]) == ("big", "high")
    assert shown["tier_models"] == {"haiku": "small", "opus": "big"}
    assert "fast_model" not in shown

    cleared = _runner.invoke(cli_app, ["agent", "edit", "codex", "--clear-tiers"])
    assert cleared.exit_code == 0, cleared.output
    shown = json.loads(_runner.invoke(cli_app, ["agent", "show", "codex", "--json"]).output)
    assert shown["tier_models"] is None
    assert (shown["model"], shown["effort"]) == ("big", "high"), "clearing tiers keeps the rest"


def test_agent_edit_binding_a_model_leaves_the_config_dir_alone(agent_cli_daemon):
    """A PATCH that omits `config_dir` must preserve the override — the route
    says so, and the CLI must not send one it was never given."""
    config_dir = _add_codex(agent_cli_daemon)
    assert _runner.invoke(cli_app, ["agent", "edit", "codex", "--model", "big"]).exit_code == 0
    shown = json.loads(_runner.invoke(cli_app, ["agent", "show", "codex", "--json"]).output)
    assert shown["config_dir"] == str(config_dir)


def test_agent_edit_rejects_a_wire_api_codex_cannot_load(agent_cli_daemon):
    """`chat` makes Codex fail to load config.toml at all. The domain refuses
    it; the CLI must surface that as a readable error, not a traceback."""
    _add_codex(agent_cli_daemon)
    bad = _runner.invoke(cli_app, ["agent", "edit", "codex", "--wire-api", "chat"])
    combined = bad.output + (bad.stderr or "")
    # 6 = INVALID_INPUT, i.e. the daemon refused the value — not 2, which is
    # what typer returns for an option the command does not have at all.
    assert bad.exit_code == 6, combined
    assert "Traceback" not in combined, combined
    assert "responses" in combined, combined


def test_agent_show_reports_the_model_binding(agent_cli_daemon):
    """A write with no read is half a surface: `show` is where a terminal user
    checks what the projector will actually write."""
    _add_codex(agent_cli_daemon)
    bound = _runner.invoke(cli_app, ["agent", "edit", "codex", "--model", "gpt-5-codex"])
    assert bound.exit_code == 0, bound.output
    shown = _runner.invoke(cli_app, ["agent", "show", "codex"])
    assert shown.exit_code == 0, shown.output
    assert "gpt-5-codex" in shown.output


# ---------------------------------------------------------------------------
# agent show — coffer_connection, through the full app with memory switched on
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_daemon(tmp_path, monkeypatch):
    from ._real_app import boot

    # `agent connect` writes the gateway entry, which names the shim binary.
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    yield from boot(tmp_path, monkeypatch)


@pytest.mark.acceptance(
    spec="memory", scenario="the agent's command-line view reports delivery state"
)
@pytest.mark.acceptance(spec="agent-registry", scenario="agent reads print JSON with --json")
def test_agent_show_reports_the_connection_part_by_part(memory_daemon, tmp_path):
    # One agent per type: Claude Code gets connected, Codex stays disconnected.
    for agent_type in ("claude_code", "codex"):
        config_dir = tmp_path / f"cfg-{agent_type}"
        (config_dir / "skills").mkdir(parents=True)
        added = _runner.invoke(
            cli_app, ["agent", "add", agent_type, "--config-dir", str(config_dir)]
        )
        assert added.exit_code == 0, added.output

    def show(ref: str) -> dict:
        out = _runner.invoke(cli_app, ["agent", "show", ref, "--json"]).output
        return dict(json.loads(_extract_json(out)))

    without = show("codex")
    connected = _runner.invoke(cli_app, ["agent", "connect", "claude-code"])
    assert connected.exit_code == 0, connected.output

    with_ = show("claude-code")
    parts = {p["key"]: p["installed"] for p in with_["coffer_connection"]["parts"]}
    assert with_["coffer_connection"]["state"] == "connected"
    assert parts == {"mcp": True, "memory_hook": True}
    assert without["coffer_connection"]["state"] == "disconnected"
    for data in (with_, without):
        assert "last_fired" not in json.dumps(data["coffer_connection"])
        assert {"name", "display_name", "type", "config_dir", "uid", "coffer_connection"} <= set(
            data
        )
        assert "title" not in data
    listed = json.loads(_extract_json(_runner.invoke(cli_app, ["agent", "list", "--json"]).output))[
        "resources"
    ]
    assert {(a["name"], a["display_name"], a["type"]) for a in listed} == {
        ("claude-code", "Claude Code", "claude_code"),
        ("codex", "OpenAI Codex", "codex"),
    }
    text = _runner.invoke(cli_app, ["agent", "show", "claude-code"]).output
    assert "coffer_connection: connected" in text
    assert "memory delivery hook: installed" in text
