"""Integration tests for `coffer agent config ...` and `coffer agent mcp ...`.

Covers the spec scenario "config-file and MCP operations mirror across
surfaces": each CLI subcommand calls the corresponding REST endpoint.

The commands under test live in ``surfaces/cli/agent_config_cmd.py`` (whole
files) and ``surfaces/cli/agent_workspace_cmd.py`` (directory children); both
attach onto the typer ``agent_cmd`` owns, so the user-facing tree is still
``coffer agent config ...`` and the invocations below are unchanged by the
split. It matters in one place: a test that reaches into a module to patch
``click.edit`` has to reach into the module the command is actually written in.

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
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.agent.config_file_service import AgentConfigFileService
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
from coffer.surfaces.http.agent_dependencies import (
    get_agent_config_file_service,
    get_agent_mcp_service,
)
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
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
    # Name → uid resolution runs before every command below and lives here, on
    # the framework's shared router. The SAME ResourceService the AgentService
    # was built on — a second one would have its own session and the resolver
    # would search a registry ``cc`` was never registered into.
    app.include_router(resource_router)
    app.dependency_overrides[get_agent_config_file_service] = lambda: config_files
    app.dependency_overrides[get_agent_mcp_service] = lambda: mcp
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


@pytest.mark.acceptance(
    spec="agent-registry", scenario="config-file and MCP operations mirror across surfaces"
)
def test_config_ls_json(agent_config_cli):
    result = _runner.invoke(cli_app, ["agent", "config", "ls", "cc", "--json"])
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    # v2 allowlist for claude_code: file entries + the subagents directory entry.
    assert [i["key"] for i in items] == [
        "settings",
        "settings_local",
        "global",
        "instructions",
        "subagents",
    ]
    by_key = {i["key"]: i for i in items}
    assert by_key["settings"]["kind"] == "file"
    assert by_key["subagents"]["kind"] == "directory"
    # Directory entries carry a `files` listing (null while the dir is absent).
    assert "files" in by_key["subagents"]


def test_config_cat_reads_existing_file(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    (tmp_path / ".claude" / "settings.json").write_text('{"x": 1}', encoding="utf-8")
    r = _runner.invoke(cli_app, ["agent", "config", "cat", "cc", "settings"])
    assert r.exit_code == 0
    assert r.output.strip() == '{"x": 1}'


def test_config_cat_unknown_key_exit4(agent_config_cli):
    """A bad config KEY exits 4 — and says so about the key, not the agent.

    Two different 404s reach exit 4 now: the agent's name failing to resolve,
    and the key failing to exist once it has. The agent here is real, so the
    message must be about the key; a message naming the agent would mean
    resolution had silently gone wrong and the test would be passing on the
    wrong failure.
    """
    r = _runner.invoke(cli_app, ["agent", "config", "cat", "cc", "nope"])
    assert r.exit_code == 4
    assert "no agent named" not in (r.output + (r.stderr or ""))


def test_config_unknown_agent_name_exit4(agent_config_cli):
    """An unheld agent name stops at resolution, before any config route.

    Same exit code the config routes' own 404 produces, from one step earlier
    and with a message naming what was actually typed — the whole reason the
    name is resolved up front rather than handed to a route that would 404 on a
    uid the user never saw (ADR resource-identity-is-an-immutable-uid).
    """
    r = _runner.invoke(cli_app, ["agent", "config", "ls", "ghost"])
    assert r.exit_code == 4, r.output
    assert "no agent named 'ghost'" in (r.output + (r.stderr or ""))


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
# agent config files / write / rm (directory entries)
# ---------------------------------------------------------------------------


def test_config_files_write_and_rm_roundtrip(agent_config_cli):
    """`config write` creates a child file, `files` lists it, `rm` deletes it."""
    tmp_path, _shim = agent_config_cli
    src = tmp_path / "reviewer.md"
    src.write_text("# Reviewer\n", encoding="utf-8")

    r = _runner.invoke(
        cli_app,
        ["agent", "config", "write", "cc", "subagents", "reviewer.md", "--from-file", str(src)],
    )
    assert r.exit_code == 0, r.output
    assert "saved: subagents/reviewer.md" in r.output
    assert (tmp_path / ".claude" / "agents" / "reviewer.md").read_text(
        encoding="utf-8"
    ) == "# Reviewer\n"

    r = _runner.invoke(cli_app, ["agent", "config", "files", "cc", "subagents", "--json"])
    assert r.exit_code == 0, r.output
    files = json.loads(r.output)
    assert [f["relpath"] for f in files] == ["reviewer.md"]

    r = _runner.invoke(
        cli_app, ["agent", "config", "rm", "cc", "subagents", "reviewer.md", "--force"]
    )
    assert r.exit_code == 0, r.output
    assert not (tmp_path / ".claude" / "agents" / "reviewer.md").exists()

    r = _runner.invoke(cli_app, ["agent", "config", "files", "cc", "subagents", "--json"])
    assert json.loads(r.output) == []


def test_config_write_from_stdin(agent_config_cli):
    """Without --from-file the content is read from stdin."""
    tmp_path, _shim = agent_config_cli
    r = _runner.invoke(
        cli_app,
        ["agent", "config", "write", "cc", "subagents", "helper.md"],
        input="# Helper\n",
    )
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".claude" / "agents" / "helper.md").read_text(
        encoding="utf-8"
    ) == "# Helper\n"


def test_config_files_non_directory_key_exit6(agent_config_cli):
    """`config files` on a plain file entry is rejected with exit 6."""
    r = _runner.invoke(cli_app, ["agent", "config", "files", "cc", "settings"])
    assert r.exit_code == 6, r.output


def test_config_rm_without_force_aborts(agent_config_cli):
    """Without --force the prompt aborts and the child file survives."""
    tmp_path, _shim = agent_config_cli
    child = tmp_path / ".claude" / "agents" / "keep.md"
    child.parent.mkdir(parents=True, exist_ok=True)
    child.write_text("# Keep\n", encoding="utf-8")

    r = _runner.invoke(
        cli_app, ["agent", "config", "rm", "cc", "subagents", "keep.md"], input="n\n"
    )
    assert r.exit_code == 1
    assert child.exists()


def test_mcp_install_status_uninstall(agent_config_cli):
    _tmp, shim = agent_config_cli
    r = _runner.invoke(cli_app, ["agent", "mcp", "status", "cc", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output)["installed"] is False

    r = _runner.invoke(cli_app, ["agent", "mcp", "install", "cc"])
    assert r.exit_code == 0, r.output
    # The echo reports the agent by the label that was typed — the uid it
    # resolved to is an address, and a person reading this line is checking
    # which agent they just changed.
    assert "installed Coffer MCP into agent cc (" in r.output
    assert shim in r.output

    r = _runner.invoke(cli_app, ["agent", "mcp", "status", "cc", "--json"])
    assert json.loads(r.output)["installed"] is True

    r = _runner.invoke(cli_app, ["agent", "mcp", "uninstall", "cc"])
    assert r.exit_code == 0
    assert "removed Coffer MCP from agent cc" in r.output
    r = _runner.invoke(cli_app, ["agent", "mcp", "status", "cc", "--json"])
    assert json.loads(r.output)["installed"] is False


def test_config_cat_json_prints_the_full_response(agent_config_cli):
    """spec agent-registry "Offer JSON output on every CLI read": ``cat --json``
    prints the whole read — content plus the fingerprint a later write needs."""
    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"x": 1}', encoding="utf-8")
    r = _runner.invoke(cli_app, ["agent", "config", "cat", "cc", "settings", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["key"] == "settings"
    assert data["content"] == '{"x": 1}'
    assert data["exists"] is True
    assert data["path"] == str(settings)
    assert data["format"] == "json"
    assert isinstance(data["fingerprint"], str) and data["fingerprint"]


def test_config_key_help_names_real_keys(agent_config_cli):
    for cmd in ("cat", "edit"):
        r = _runner.invoke(cli_app, ["agent", "config", cmd, "--help"])
        assert r.exit_code == 0, r.output
        # Rich wraps help inside a box; flatten borders and line breaks first.
        flat = " ".join(r.output.replace("│", " ").split())
        assert "settings, config, instructions" in flat
        assert "memory" not in flat


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
