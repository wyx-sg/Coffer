"""CLI coverage for `coffer agent hook ...` and `agent native-memory ...` (Slice 6)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC
from datetime import datetime as dt

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.application.agent.hook_service import AgentHookService
from coffer.application.agent.kind import make_agent_kind
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
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import agent_config_routes, agent_routes
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_agent_hook_service, get_agent_service

_runner = CliRunner()
_TOKEN = "test-token-hook-cli"


@pytest.fixture
def hook_cli_daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    hook = tmp_path / "coffer-hook"
    hook.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_HOOK_PATH", str(hook))

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_create_tables(engine))
    finally:
        loop.close()

    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    kinds = {"agent": make_agent_kind(on_delete=None)}
    rs = ResourceService(kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    store = ConfigFileStore()
    agent_svc = AgentService(resource_service=rs, audit=audit, config_file_store=store)
    hook_svc = AgentHookService(
        agent_service=agent_svc,
        audit=audit,
        store=store,
        hook_resolver=lambda: str(hook),
    )

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            agent_svc.register(agent_type=AgentType.CLAUDE_CODE, name="cc", actor="cli")
        )
    finally:
        loop.close()

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_routes.router)
    app.include_router(agent_config_routes.router)
    app.dependency_overrides[get_agent_service] = lambda: agent_svc
    app.dependency_overrides[get_agent_hook_service] = lambda: hook_svc

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


def test_hook_status_install_uninstall(hook_cli_daemon):
    r = _runner.invoke(cli_app, ["agent", "hook", "status", "cc", "--json"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["installed"] is False

    r = _runner.invoke(cli_app, ["agent", "hook", "install", "cc"])
    assert r.exit_code == 0, r.output
    assert "installed Coffer hooks" in r.output

    r = _runner.invoke(cli_app, ["agent", "hook", "status", "cc", "--json"])
    assert json.loads(r.output)["installed"] is True

    r = _runner.invoke(cli_app, ["agent", "hook", "uninstall", "cc"])
    assert r.exit_code == 0, r.output
    assert (
        _runner.invoke(cli_app, ["agent", "hook", "status", "cc", "--json"]).output
        and json.loads(_runner.invoke(cli_app, ["agent", "hook", "status", "cc", "--json"]).output)[
            "installed"
        ]
        is False
    )


def test_edit_disable_enable_native_memory(hook_cli_daemon):
    r = _runner.invoke(cli_app, ["agent", "edit", "cc", "--disable-native-memory"])
    assert r.exit_code == 0, r.output
    settings = json.loads((hook_cli_daemon / ".claude" / "settings.json").read_text())
    assert settings["autoMemoryEnabled"] is False
    assert json.loads(_runner.invoke(cli_app, ["agent", "show", "cc", "--json"]).output)

    r = _runner.invoke(cli_app, ["agent", "edit", "cc", "--enable-native-memory"])
    assert r.exit_code == 0, r.output
    settings = json.loads((hook_cli_daemon / ".claude" / "settings.json").read_text())
    assert "autoMemoryEnabled" not in settings
