"""Integration tests for `coffer agent instructions` CLI subcommands (spec 004).

Same in-process-daemon strategy as ``test_agent_cmd.py``: a tiny FastAPI app
wired to a real ``AgentService`` + ``AgentInstructionsService`` over an in-tree
SQLite DB, with ``_client.client_or_exit`` patched to a TestClient. The CLI
verbs therefore exercise the same HTTP routes the desktop UI consumes.
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
from coffer.application.agent.instructions_service import AgentInstructionsService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
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
from coffer.surfaces.http.agent_instructions_routes import (
    agent_instructions_router,
    get_agent_instructions_service,
    master_router,
)
from coffer.surfaces.http.agent_routes import router as agent_router
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_agent_service

_runner = CliRunner()
_TOKEN = "test-token-instr-cli"


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def instr_cli_daemon(tmp_path, monkeypatch):
    """In-process daemon with agent + instructions routers; patches client_or_exit."""
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
    instr_svc = AgentInstructionsService(
        agent_service=agent_svc, audit=audit, store=ConfigFileStore()
    )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_router)
    app.include_router(master_router)
    app.include_router(agent_instructions_router)
    app.dependency_overrides[get_agent_service] = lambda: agent_svc
    app.dependency_overrides[get_agent_instructions_service] = lambda: instr_svc

    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1, pid=12345, port=8000, token=_TOKEN, started_at=dt.now(tz=UTC), binary_path="/t"
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


def _register_claude(tmp_path) -> None:
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    r = _runner.invoke(cli_app, ["agent", "add", "claude_code"])
    assert r.exit_code == 0, r.output


def test_master_empty_then_set_and_read(instr_cli_daemon):
    """`instructions master` reads empty, `set-master --file` writes, read reflects it."""
    tmp = instr_cli_daemon
    # Empty on a fresh install (JSON form).
    r = _runner.invoke(cli_app, ["agent", "instructions", "master", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["content"] == ""

    src = tmp / "rules.md"
    src.write_text("house rules\n", encoding="utf-8")
    s = _runner.invoke(cli_app, ["agent", "instructions", "set-master", "--file", str(src)])
    assert s.exit_code == 0, s.output
    assert "master instructions updated" in s.output

    r2 = _runner.invoke(cli_app, ["agent", "instructions", "master"])
    assert r2.exit_code == 0, r2.output
    assert "house rules" in r2.output


def test_deliver_status_remove_roundtrip(instr_cli_daemon):
    """deliver → status (delivered/in_sync) → remove, all via the CLI."""
    tmp = instr_cli_daemon
    _register_claude(tmp)
    src = tmp / "m.md"
    src.write_text("BODY\n", encoding="utf-8")
    _runner.invoke(cli_app, ["agent", "instructions", "set-master", "--file", str(src)])

    d = _runner.invoke(cli_app, ["agent", "instructions", "deliver", "claude-code"])
    assert d.exit_code == 0, d.output
    assert "delivered master instructions to agent:claude-code" in d.output
    assert "BODY" in (tmp / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")

    st = _runner.invoke(cli_app, ["agent", "instructions", "status", "claude-code", "--json"])
    assert st.exit_code == 0, st.output
    assert json.loads(st.output) == {"delivered": True, "in_sync": True}

    rm = _runner.invoke(cli_app, ["agent", "instructions", "remove", "claude-code"])
    assert rm.exit_code == 0, rm.output
    assert "removed delivered instructions" in rm.output


def test_adopt_sets_master_from_agent(instr_cli_daemon):
    """`instructions adopt` pulls the agent's instructions into the master."""
    tmp = instr_cli_daemon
    _register_claude(tmp)
    (tmp / ".claude" / "CLAUDE.md").write_text("adopt me\n", encoding="utf-8")
    a = _runner.invoke(cli_app, ["agent", "instructions", "adopt", "claude-code"])
    assert a.exit_code == 0, a.output
    assert "adopted agent:claude-code instructions into the master" in a.output
    m = _runner.invoke(cli_app, ["agent", "instructions", "master"])
    assert "adopt me" in m.output


def test_status_unsupported_agent_exits_nonzero(instr_cli_daemon):
    """An agent type without an instructions file fails cleanly (422 → non-zero exit)."""
    tmp = instr_cli_daemon
    (tmp / ".openclaw").mkdir(parents=True, exist_ok=True)
    _runner.invoke(cli_app, ["agent", "add", "openclaw"])
    r = _runner.invoke(cli_app, ["agent", "instructions", "status", "openclaw"])
    assert r.exit_code != 0


def test_set_master_stale_fingerprint_rejected(instr_cli_daemon):
    """`set-master --expected-fingerprint` with an outdated value fails (409 → non-zero)."""
    tmp = instr_cli_daemon
    src = tmp / "r.md"
    src.write_text("v1\n", encoding="utf-8")
    ok = _runner.invoke(cli_app, ["agent", "instructions", "set-master", "--file", str(src)])
    assert ok.exit_code == 0, ok.output
    stale = _runner.invoke(
        cli_app,
        ["agent", "instructions", "set-master", "--file", str(src), "--expected-fingerprint", "x"],
    )
    assert stale.exit_code != 0
