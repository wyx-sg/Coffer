"""Integration tests for `coffer agent config ...` and `coffer agent mcp ...`.

Covers the spec scenario "config-file and MCP operations mirror across
surfaces": each CLI subcommand calls the corresponding REST endpoint.
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
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import (
    get_agent_config_file_service,
    get_agent_mcp_service,
)

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
    app.dependency_overrides[get_agent_config_file_service] = lambda: config_files
    app.dependency_overrides[get_agent_mcp_service] = lambda: mcp

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
    spec="004-agent-registry", scenario="config-file and MCP operations mirror across surfaces"
)
def test_config_ls_json(agent_config_cli):
    result = _runner.invoke(cli_app, ["agent", "config", "ls", "cc", "--json"])
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert [i["key"] for i in items] == ["settings", "settings_local", "global", "memory"]


def test_config_cat_reads_existing_file(agent_config_cli):
    tmp_path, _shim = agent_config_cli
    (tmp_path / ".claude" / "settings.json").write_text('{"x": 1}', encoding="utf-8")
    r = _runner.invoke(cli_app, ["agent", "config", "cat", "cc", "settings"])
    assert r.exit_code == 0
    assert r.output.strip() == '{"x": 1}'


def test_config_cat_unknown_key_exit4(agent_config_cli):
    r = _runner.invoke(cli_app, ["agent", "config", "cat", "cc", "nope"])
    assert r.exit_code == 4


@pytest.mark.acceptance(spec="004-agent-registry", scenario="save a config file with valid content")
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
    non-existent `typer.edit` and crashed with AttributeError."""
    import coffer.surfaces.cli.agent_cmd as agent_cmd

    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake_edit(text, extension=None):
        captured["text"] = text
        captured["extension"] = extension
        return '{"theme": "dark"}'

    monkeypatch.setattr(agent_cmd.click, "edit", _fake_edit)

    r = _runner.invoke(cli_app, ["agent", "config", "edit", "cc", "settings"])
    assert r.exit_code == 0, r.output
    assert captured["text"] == '{"theme": "light"}'  # current content seeded
    assert captured["extension"] == ".settings"
    assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}'


def test_config_edit_interactive_no_changes(agent_config_cli, monkeypatch):
    """click.edit returns None when the user makes no change / aborts — the
    command exits 0 without writing."""
    import coffer.surfaces.cli.agent_cmd as agent_cmd

    tmp_path, _shim = agent_config_cli
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"theme": "light"}', encoding="utf-8")

    monkeypatch.setattr(agent_cmd.click, "edit", lambda text, extension=None: None)

    r = _runner.invoke(cli_app, ["agent", "config", "edit", "cc", "settings"])
    assert r.exit_code == 0, r.output
    assert settings.read_text(encoding="utf-8") == '{"theme": "light"}'  # untouched
    assert not (tmp_path / ".claude" / "settings.json.bak").exists()


@pytest.mark.acceptance(spec="004-agent-registry", scenario="reject malformed config-file content")
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


def test_mcp_install_status_uninstall(agent_config_cli):
    _tmp, shim = agent_config_cli
    r = _runner.invoke(cli_app, ["agent", "mcp", "status", "cc", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.output)["installed"] is False

    r = _runner.invoke(cli_app, ["agent", "mcp", "install", "cc"])
    assert r.exit_code == 0, r.output
    assert shim in r.output

    r = _runner.invoke(cli_app, ["agent", "mcp", "status", "cc", "--json"])
    assert json.loads(r.output)["installed"] is True

    r = _runner.invoke(cli_app, ["agent", "mcp", "uninstall", "cc"])
    assert r.exit_code == 0
    r = _runner.invoke(cli_app, ["agent", "mcp", "status", "cc", "--json"])
    assert json.loads(r.output)["installed"] is False
