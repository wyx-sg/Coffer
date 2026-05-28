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
from coffer.infrastructure.agent.persistence import SuppressedAgentTypeRepo
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
    suppression = SuppressedAgentTypeRepo(sm)
    agent_svc = AgentService(
        resource_service=resource_svc, audit=audit, suppression_repo=suppression
    )
    detect_svc = AutoDetectService(
        agent_service=agent_svc, audit=audit, suppression_repo=suppression
    )

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
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        [
            "agent",
            "add",
            "cursor",
            "--name",
            "cur",
            "--skill-dir",
            str(skill_dir),
        ],
    )
    result = _runner.invoke(cli_app, ["agent", "list"])
    assert result.exit_code == 0, result.output
    # Table title must be present in the rendered output.
    assert "Agents" in result.output
    assert "cur" in result.output


def test_agent_list_shows_registered_json(agent_cli_daemon):
    """`agent list --json` includes a previously-registered agent."""
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(skill_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "list", "--json"])
    assert result.exit_code == 0
    items = json.loads(result.output)
    assert len(items) == 1
    assert items[0]["name"] == "cur"
    assert items[0]["type"] == "cursor"


# ---------------------------------------------------------------------------
# agent add
# ---------------------------------------------------------------------------


def test_agent_add_success(agent_cli_daemon):
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    result = _runner.invoke(
        cli_app,
        [
            "agent",
            "add",
            "cursor",
            "--name",
            "cur",
            "--skill-dir",
            str(skill_dir),
            "--description",
            "manual",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "registered" in result.output


def test_agent_add_duplicate_fails(agent_cli_daemon):
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(skill_dir)],
    )
    result = _runner.invoke(
        cli_app,
        [
            "agent",
            "add",
            "claude_code",
            "--name",
            "cur",
            "--skill-dir",
            str(skill_dir),
        ],
    )
    # add() routes 4xx through _cli_client.check, which maps 409 →
    # ExitCode.CONFLICT (5). CODE25-018 — fix-validation.
    assert result.exit_code == 5, result.output


# ---------------------------------------------------------------------------
# agent show
# ---------------------------------------------------------------------------


def test_agent_show_existing_text(agent_cli_daemon):
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(skill_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "show", "cur"])
    assert result.exit_code == 0, result.output
    assert "name: cur" in result.output
    assert "type: cursor" in result.output


def test_agent_show_existing_json(agent_cli_daemon):
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(skill_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "show", "cur", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["name"] == "cur"
    assert data["type"] == "cursor"
    assert data["skill_dir"] == str(skill_dir)


def test_agent_show_not_found(agent_cli_daemon):
    result = _runner.invoke(cli_app, ["agent", "show", "ghost"])
    assert result.exit_code == 4, result.output


# ---------------------------------------------------------------------------
# agent edit
# ---------------------------------------------------------------------------


def test_agent_edit_skill_dir(agent_cli_daemon):
    old = agent_cli_daemon / "skills"
    new = agent_cli_daemon / "skills2"
    old.mkdir()
    new.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(old)],
    )
    result = _runner.invoke(cli_app, ["agent", "edit", "cur", "--skill-dir", str(new)])
    assert result.exit_code == 0, result.output
    assert "updated" in result.output
    # And the new skill_dir was actually persisted.
    show = _runner.invoke(cli_app, ["agent", "show", "cur", "--json"])
    data = json.loads(show.output)
    assert data["skill_dir"] == str(new)


def test_agent_edit_no_fields_exits_1(agent_cli_daemon):
    """`edit` with no flags is a no-op and exits non-zero with a clear message."""
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(skill_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "edit", "cur"])
    assert result.exit_code == 1
    assert "nothing to update" in (result.output or result.stderr or "")


def test_agent_edit_disable(agent_cli_daemon):
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(skill_dir)],
    )
    result = _runner.invoke(cli_app, ["agent", "edit", "cur", "--disabled"])
    assert result.exit_code == 0, result.output
    show = _runner.invoke(cli_app, ["agent", "show", "cur", "--json"])
    assert json.loads(show.output)["enabled"] is False


def test_agent_edit_not_found(agent_cli_daemon):
    result = _runner.invoke(cli_app, ["agent", "edit", "ghost", "--description", "x"])
    assert result.exit_code == 4


# ---------------------------------------------------------------------------
# agent rm
# ---------------------------------------------------------------------------


def test_agent_rm_force(agent_cli_daemon):
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(skill_dir)],
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
    skill_dir = agent_cli_daemon / "skills"
    skill_dir.mkdir()
    _runner.invoke(
        cli_app,
        ["agent", "add", "cursor", "--name", "cur", "--skill-dir", str(skill_dir)],
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


def test_agent_detect_registers_marker_present(agent_cli_daemon):
    """`detect` with marker dirs prints one line per newly-registered agent."""
    (agent_cli_daemon / ".cursor" / "skills").mkdir(parents=True)
    (agent_cli_daemon / ".claude" / "skills").mkdir(parents=True)
    result = _runner.invoke(cli_app, ["agent", "detect"])
    assert result.exit_code == 0, result.output
    assert "detected:" in result.output
    assert "cursor" in result.output or "claude_code" in result.output
