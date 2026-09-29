"""Integration tests for `coffer agent config edit|rm`, `coffer agent
connect|disconnect` and the `coffer_connection` field of `coffer agent show`.

Covers the spec scenario "config-file and MCP operations mirror across
surfaces": each CLI subcommand calls the corresponding REST endpoint.

The config commands live in ``surfaces/cli/agent_config_cmd.py``; a test that
patches ``click.edit`` reaches into that module, where the command is written.

The in-process app mounts TWO routers. Each of these commands takes the agent's
NAME and resolves it to the uid the routes address
(ADR resource-identity-is-an-immutable-uid) via
``GET /resources?kind=agent&name=``, which lives on the framework's resource
router rather than on ``/agents``. Serving only ``agent_config_router`` would
fail every command at resolution — and fail it with a 404 that reads like a
missing config file, so the tests would be red for a reason that has nothing to
do with what they assert.
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
from coffer.application.agent.config_file_service import AgentConfigFileService
from coffer.application.agent.connection_service import (
    AgentConnectionService,
    McpConnectionPart,
)
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
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
from coffer.surfaces.http.agent_config_routes import router as agent_config_router
from coffer.surfaces.http.agent_connection_routes import router as agent_connection_router
from coffer.surfaces.http.agent_dependencies import (
    get_agent_config_file_service,
    get_agent_connection_service,
    get_agent_service,
)
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.audit_routes import router as audit_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router

_runner = CliRunner()
_TOKEN = "test-token-agent-config-cli"


@pytest.fixture
def agent_config_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
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
    store = ConfigFileStore()
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    config_files = AgentConfigFileService(agent_service=agent_svc, audit=audit, store=store)
    mcp = AgentMcpService(
        agent_service=agent_svc, audit=audit, store=store, shim_resolver=lambda: str(shim)
    )
    # Only the gateway part: the memory hook is the memory kind's, wired by the
    # composition root and covered by test_agent_connection.py.
    connection = AgentConnectionService(agent_service=agent_svc, parts=(McpConnectionPart(mcp),))

    # Register a claude_code agent up front.
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            agent_svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")
        )
    finally:
        loop.close()

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_config_router)
    app.include_router(agent_connection_router)
    # Name → uid resolution runs before every command below and lives here, on
    # the framework's shared router. The SAME ResourceService the AgentService
    # was built on — a second one would have its own session and the resolver
    # would search a registry ``cc`` was never registered into.
    app.include_router(resource_router)
    # `agent show` reads the record from /agents; the audit route is how the
    # tests read the audit entries a write records.
    app.include_router(agent_router)
    app.include_router(audit_router)
    app.dependency_overrides[get_agent_service] = lambda: agent_svc
    app.dependency_overrides[get_audit_service] = lambda: audit
    app.dependency_overrides[get_agent_config_file_service] = lambda: config_files
    app.dependency_overrides[get_agent_connection_service] = lambda: connection
    app.dependency_overrides[get_resource_service] = lambda: resource_svc

    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1, pid=1, port=8000, token=_TOKEN, started_at=dt.now(tz=UTC), binary_path="/t"
    )
    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, info))

    yield tmp_path, str(shim)

    set_active_token(None)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(engine.dispose())
    finally:
        loop.close()


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _audit_events(event_type: str) -> list[dict]:
    client, _info = _cli_client.client_or_exit()
    r = client.get("/audit", params={"event_type": event_type})
    assert r.status_code == 200, r.text
    return list(r.json()["entries"])


def _uid(name: str = "cc") -> str:
    client, _info = _cli_client.client_or_exit()
    return str(
        client.get("/resources", params={"kind": "agent", "name": name}).json()["resources"][0][
            "uid"
        ]
    )


def test_config_edit_unknown_key_exit4(agent_config_cli):
    """A bad config KEY exits 4 — and says so about the key, not the agent.

    Two different 404s reach exit 4: the agent's name failing to resolve, and
    the key failing to exist once it has. The agent here is real, so the
    message must be about the key.
    """
    tmp_path, _shim = agent_config_cli
    src = tmp_path / "x.json"
    src.write_text("{}", encoding="utf-8")
    r = _runner.invoke(cli_app, ["agent", "config", "edit", "cc", "nope", "--from-file", str(src)])
    assert r.exit_code == 4
    assert "no agent named" not in (r.output + (r.stderr or ""))


def test_config_unknown_agent_name_exit4(agent_config_cli):
    """An unheld agent name stops at resolution, before any config route."""
    r = _runner.invoke(cli_app, ["agent", "config", "rm", "ghost", "subagents/x.md", "--yes"])
    assert r.exit_code == 4, r.output
    assert "no agent named 'ghost'" in (r.output + (r.stderr or ""))


@pytest.mark.acceptance(
    spec="agent-registry", scenario="edit a config file from a file on the command line"
)
def test_edit_a_config_file_from_a_file_on_the_command_line(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text('{"theme": "dark"}', encoding="utf-8")

    r = _runner.invoke(
        cli_app, ["agent", "config", "edit", "cc", "settings", "--from-file", str(good)]
    )
    assert r.exit_code == 0, r.output
    assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}'
    assert (tmp_path / ".claude" / "settings.json.bak").read_text(
        encoding="utf-8"
    ) == '{"theme": "light"}'
    written = _audit_events("agent_config_file_written")
    assert len(written) == 1 and written[0]["resource_name"] == "cc"

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = _runner.invoke(
        cli_app, ["agent", "config", "edit", "cc", "settings", "--from-file", str(bad)]
    )
    assert r.exit_code != 0, r.output
    assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}'
    assert len(_audit_events("agent_config_file_written")) == 1


def test_config_edit_from_file_sends_the_fingerprint_of_its_read(agent_config_cli, monkeypatch):
    """--from-file still carries the fingerprint of the read it started from, so a
    change landing between that read and the write is refused (exit 5)."""
    import coffer.surfaces.cli.agent_config_cmd as agent_config_cmd

    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")
    src = tmp_path / "new.json"
    src.write_text('{"theme": "dark"}', encoding="utf-8")
    real_read = agent_config_cmd._read_source

    def _read_while_agent_rewrites(path: str) -> str:
        settings.write_text('{"theme": "agent"}', encoding="utf-8")
        return real_read(path)

    monkeypatch.setattr(agent_config_cmd, "_read_source", _read_while_agent_rewrites)
    r = _runner.invoke(
        cli_app, ["agent", "config", "edit", "cc", "settings", "--from-file", str(src)]
    )
    assert r.exit_code == 5, r.output
    assert settings.read_text(encoding="utf-8") == '{"theme": "agent"}'


@pytest.mark.acceptance(spec="agent-registry", scenario="save a config file with valid content")
def test_config_edit_from_file_valid(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")
    src = tmp_path / "new.json"
    src.write_text('{"theme": "dark"}', encoding="utf-8")

    r = _runner.invoke(
        cli_app, ["agent", "config", "edit", "cc", "settings", "--from-file", str(src)]
    )
    assert r.exit_code == 0, r.output
    assert ".bak" in r.output
    assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}'
    assert (tmp_path / ".claude" / "settings.json.bak").read_text(
        encoding="utf-8"
    ) == '{"theme": "light"}'


def test_config_edit_interactive_editor(agent_config_cli, monkeypatch):
    """The interactive (no --from-file) path opens $EDITOR via click.edit and
    saves the returned content. Regression: this branch previously called the
    non-existent `typer.edit` and crashed with AttributeError.

    Patched on ``agent_config_cmd``, which is where ``config edit`` is written
    — ``agent_cmd`` owns the ``config`` typer but no longer imports click, so
    patching it there would raise AttributeError before the command ran.
    """
    import coffer.surfaces.cli.agent_config_cmd as agent_config_cmd

    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake_edit(text, extension=None):
        captured["text"] = text
        captured["extension"] = extension
        return '{"theme": "dark"}'

    monkeypatch.setattr(agent_config_cmd.click, "edit", _fake_edit)

    r = _runner.invoke(cli_app, ["agent", "config", "edit", "cc", "settings"])
    assert r.exit_code == 0, r.output
    assert captured["text"] == '{"theme": "light"}'  # current content seeded
    assert captured["extension"] == ".settings"
    assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}'


def test_config_edit_interactive_no_changes(agent_config_cli, monkeypatch):
    """click.edit returns None when the user makes no change / aborts — the
    command exits 0 without writing."""
    import coffer.surfaces.cli.agent_config_cmd as agent_config_cmd

    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")

    monkeypatch.setattr(agent_config_cmd.click, "edit", lambda text, extension=None: None)

    r = _runner.invoke(cli_app, ["agent", "config", "edit", "cc", "settings"])
    assert r.exit_code == 0, r.output
    assert settings.read_text(encoding="utf-8") == '{"theme": "light"}'  # untouched
    assert not (tmp_path / ".claude" / "settings.json.bak").exists()


@pytest.mark.acceptance(spec="agent-registry", scenario="reject malformed config-file content")
def test_config_edit_from_file_malformed_exit2_unchanged(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")
    src = tmp_path / "bad.json"
    src.write_text("{not json", encoding="utf-8")

    r = _runner.invoke(
        cli_app, ["agent", "config", "edit", "cc", "settings", "--from-file", str(src)]
    )
    assert r.exit_code == 2, r.output
    # File untouched.
    assert settings.read_text(encoding="utf-8") == '{"theme": "light"}'
    assert not (tmp_path / ".claude" / "settings.json.bak").exists()


# ---------------------------------------------------------------------------
# agent config edit KEY/CHILD, rm KEY/CHILD (directory entries)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="agent-registry", scenario="create a file inside a directory entry")
@pytest.mark.acceptance(spec="agent-registry", scenario="delete a file inside a directory entry")
def test_config_child_edit_and_rm_roundtrip(agent_config_cli):
    """`config edit KEY/CHILD --from-file` creates a child file, `rm` deletes it."""
    tmp_path, _shim = agent_config_cli
    child = tmp_path / ".claude" / "agents" / "reviewer.md"
    src = tmp_path / "reviewer.md"
    src.write_text("# Reviewer\n", encoding="utf-8")

    r = _runner.invoke(
        cli_app,
        ["agent", "config", "edit", "cc", "subagents/reviewer.md", "--from-file", str(src)],
    )
    assert r.exit_code == 0, r.output
    assert "saved: subagents/reviewer.md" in r.output
    assert child.read_text(encoding="utf-8") == "# Reviewer\n"
    assert len(_audit_events("agent_config_file_written")) == 1
    client, _info = _cli_client.client_or_exit()
    listing = client.get(f"/agents/{_uid()}/config-files").json()["items"]
    subagents = next(i for i in listing if i["key"] == "subagents")
    assert [f["relpath"] for f in subagents["files"]] == ["reviewer.md"]

    r = _runner.invoke(cli_app, ["agent", "config", "rm", "cc", "subagents/reviewer.md", "--force"])
    assert r.exit_code == 0, r.output
    assert not child.exists()
    assert child.with_name("reviewer.md.bak").read_text(encoding="utf-8") == "# Reviewer\n"
    assert len(_audit_events("agent_config_file_deleted")) == 1
    listing = client.get(f"/agents/{_uid()}/config-files").json()["items"]
    subagents = next(i for i in listing if i["key"] == "subagents")
    assert not subagents["files"]


def test_config_child_edit_from_stdin(agent_config_cli):
    """`--from-file -` reads the content from stdin."""
    tmp_path, _shim = agent_config_cli
    r = _runner.invoke(
        cli_app,
        ["agent", "config", "edit", "cc", "subagents/helper.md", "--from-file", "-"],
        input="# Helper\n",
    )
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".claude" / "agents" / "helper.md").read_text(
        encoding="utf-8"
    ) == "# Helper\n"


def test_config_child_of_a_plain_file_entry_exits_4(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    src = tmp_path / "x.md"
    src.write_text("x", encoding="utf-8")
    r = _runner.invoke(
        cli_app, ["agent", "config", "edit", "cc", "settings/x.md", "--from-file", str(src)]
    )
    assert r.exit_code == 4, r.output


def test_config_rm_needs_a_child(agent_config_cli):
    r = _runner.invoke(cli_app, ["agent", "config", "rm", "cc", "settings", "--yes"])
    assert r.exit_code == 2, r.output


def test_config_rm_without_force_aborts(agent_config_cli):
    """Without --force the prompt aborts and the child file survives."""
    tmp_path, _shim = agent_config_cli
    child = tmp_path / ".claude" / "agents" / "keep.md"
    child.parent.mkdir(parents=True, exist_ok=True)
    child.write_text("# Keep\n", encoding="utf-8")

    r = _runner.invoke(cli_app, ["agent", "config", "rm", "cc", "subagents/keep.md"], input="n\n")
    assert r.exit_code == 1
    assert child.exists()


# ---------------------------------------------------------------------------
# agent connect / disconnect / show (coffer_connection)
# ---------------------------------------------------------------------------


def _show(name: str = "cc") -> dict:
    r = _runner.invoke(cli_app, ["agent", "show", name, "--json"])
    assert r.exit_code == 0, r.output
    return dict(json.loads(r.output))


@pytest.mark.acceptance(
    spec="agent-registry", scenario="connect an agent to Coffer from the command line"
)
def test_connect_an_agent_to_coffer_from_the_command_line(agent_config_cli):
    tmp_path, shim = agent_config_cli
    r = _runner.invoke(cli_app, ["agent", "connect", "cc"])
    assert r.exit_code == 0, r.output
    assert "connected agent cc to Coffer" in r.output
    assert f"gateway MCP entry: installed ({shim})" in r.output
    mcp_config = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
    entry = mcp_config["mcpServers"]["coffer"]
    assert _uid() in entry["args"]
    installed = _audit_events("agent_mcp_installed")
    assert len(installed) == 1 and installed[0]["resource_name"] == "cc"


@pytest.mark.acceptance(
    spec="agent-registry", scenario="disconnect an agent from Coffer on the command line"
)
def test_disconnect_an_agent_from_coffer_on_the_command_line(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    assert _runner.invoke(cli_app, ["agent", "connect", "cc"]).exit_code == 0

    r = _runner.invoke(cli_app, ["agent", "disconnect", "cc"])
    assert r.exit_code == 0, r.output
    assert "disconnected agent cc from Coffer" in r.output
    mcp_config = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
    assert "coffer" not in mcp_config.get("mcpServers", {})
    assert _show()["coffer_connection"]["state"] == "disconnected"
    text = _runner.invoke(cli_app, ["agent", "show", "cc"]).output
    assert "coffer_connection: not connected" in text


@pytest.mark.acceptance(spec="agent-registry", scenario="agent show reports the Coffer MCP status")
def test_agent_show_reports_the_coffer_connection(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    other_dir = tmp_path / "other-claude"
    (other_dir / "skills").mkdir(parents=True)
    added = _runner.invoke(
        cli_app,
        ["agent", "add", "claude_code", "--name", "other", "--config-dir", str(other_dir)],
    )
    assert added.exit_code == 0, added.output
    assert _runner.invoke(cli_app, ["agent", "connect", "cc"]).exit_code == 0

    assert _show("cc")["coffer_connection"]["state"] == "connected"
    assert _show("other")["coffer_connection"]["state"] == "disconnected"
    text = _runner.invoke(cli_app, ["agent", "show", "cc"]).output
    assert "coffer_connection: connected" in text
    assert "gateway MCP entry: installed" in text


@pytest.mark.acceptance(
    spec="agent-registry", scenario="config-file and MCP operations mirror across surfaces"
)
def test_config_and_mcp_commands_mirror_their_rest_routes(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    client, _info = _cli_client.client_or_exit()
    uid = _uid()
    status = f"/agents/{uid}/coffer-connection"

    assert _runner.invoke(cli_app, ["agent", "connect", "cc"]).exit_code == 0
    assert client.get(status).json()["state"] == "connected"
    assert _show()["coffer_connection"] == client.get(status).json()
    assert _runner.invoke(cli_app, ["agent", "disconnect", "cc"]).exit_code == 0
    assert client.get(status).json()["state"] == "disconnected"
    assert _show()["coffer_connection"] == client.get(status).json()

    src = tmp_path / "s.json"
    src.write_text('{"a": 1}', encoding="utf-8")
    r = _runner.invoke(
        cli_app, ["agent", "config", "edit", "cc", "settings", "--from-file", str(src)]
    )
    assert r.exit_code == 0, r.output
    assert client.get(f"/agents/{uid}/config-files/settings").json()["content"] == '{"a": 1}'

    child = tmp_path / "c.md"
    child.write_text("# c\n", encoding="utf-8")
    edit_child = ["agent", "config", "edit", "cc", "subagents/c.md", "--from-file", str(child)]
    assert _runner.invoke(cli_app, edit_child).exit_code == 0
    read = client.get(f"/agents/{uid}/config-files/subagents/files/c.md").json()
    assert read["exists"] is True
    rm = _runner.invoke(cli_app, ["agent", "config", "rm", "cc", "subagents/c.md", "--yes"])
    assert rm.exit_code == 0, rm.output
    read = client.get(f"/agents/{uid}/config-files/subagents/files/c.md").json()
    assert read["exists"] is False


def test_config_key_help_names_real_keys(agent_config_cli):
    # The KEY argument's own help, read off the command rather than out of the
    # rendered --help, whose layout changes between typer/rich releases.
    edit = typer.main.get_command(cli_app).commands["agent"].commands["config"].commands["edit"]  # type: ignore[attr-defined]
    help_text = (
        " ".join(" ".join(str(getattr(p, "help", "") or "").split()) for p in edit.params)
        + " "
        + " ".join((edit.help or "").split())
    )
    assert "settings, config, instructions" in help_text
    assert "memory" not in help_text


def test_config_edit_refuses_when_the_file_changed_since_its_read(agent_config_cli, monkeypatch):
    """spec agent-registry "Reject stale config-file writes by fingerprint": the
    edit carries the fingerprint of the content it opened, so a change made on
    disk while the editor was open is a conflict, not a silent overwrite."""
    import coffer.surfaces.cli.agent_config_cmd as agent_config_cmd

    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")

    def _edit_while_agent_rewrites(text, extension=None):
        # The agent's own process rewrites the file while $EDITOR is open.
        settings.write_text('{"theme": "agent"}', encoding="utf-8")
        return '{"theme": "dark"}'

    monkeypatch.setattr(agent_config_cmd.click, "edit", _edit_while_agent_rewrites)

    r = _runner.invoke(cli_app, ["agent", "config", "edit", "cc", "settings"])
    assert r.exit_code == 5, r.output
    assert "changed on disk since last read" in (r.output + (r.stderr or ""))
    assert "saved" not in r.output
    # The other process's content survives; no Coffer write, so no .bak.
    assert settings.read_text(encoding="utf-8") == '{"theme": "agent"}'
    assert not (tmp_path / ".claude" / "settings.json.bak").exists()
