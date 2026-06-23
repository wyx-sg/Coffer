"""`coffer provider …` CLI coverage (spec 011).

Wires a minimal provider-only in-process daemon and monkeypatches
``client_or_exit`` to a Starlette TestClient over it (mirrors the conftest's
``in_proc_daemon`` pattern).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.application.audit_service import AuditService
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.service import ProviderService
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_provider_service
from coffer.surfaces.http.provider_routes import router as provider_router

_runner = CliRunner()
_TOKEN = "test-token-011-cli"


class _DictStore:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self._d.get(ref)

    def set(self, ref: str, value: str) -> None:
        self._d[ref] = value

    def delete(self, ref: str) -> None:
        self._d.pop(ref, None)


class _NoAgents:
    async def list(self):
        return []


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def provider_daemon(tmp_path, monkeypatch):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create_tables(engine))
    loop.close()
    sm = session_maker(engine)
    store = _DictStore()
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"provider": make_provider_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        credentials=store,
    )
    provider_svc = ProviderService(
        resources=resources,
        credentials=store,
        config_store=ConfigFileStore(),
        agents=_NoAgents(),
        audit=audit,
    )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(provider_router)
    app.dependency_overrides[get_provider_service] = lambda: provider_svc
    set_active_token(_TOKEN)

    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, object()))
    yield
    set_active_token(None)


@pytest.mark.acceptance(
    spec="011-provider-switching", scenario="the command line covers create, list, and switch"
)
def test_cli_create_list_switch(provider_daemon):
    r = _runner.invoke(
        cli_app,
        [
            "provider",
            "add",
            "acme",
            "--protocol",
            "anthropic",
            "--base-url",
            "https://gw/anthropic",
            "--secret",
            "sk-x",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "added provider acme" in r.output

    r = _runner.invoke(cli_app, ["provider", "list", "--json"])
    assert r.exit_code == 0, r.output
    assert [p["name"] for p in json.loads(r.output)["providers"]] == ["acme"]

    r = _runner.invoke(cli_app, ["provider", "switch", "acme"])
    assert r.exit_code == 0, r.output
    assert "switched to acme" in r.output


def test_cli_key_by_connection_and_compatible(provider_daemon):
    # An openai gateway routed to Claude Code via --compatible.
    r = _runner.invoke(
        cli_app,
        [
            "provider",
            "add",
            "agnes",
            "--protocol",
            "openai",
            "--base-url",
            "https://agnes/v1",
            "--secret",
            "sk-agnes",
            "--compatible",
            "claude_code",
        ],
    )
    assert r.exit_code == 0, r.output

    show = _runner.invoke(cli_app, ["provider", "show", "agnes"])
    assert json.loads(show.output)["compatible_agents"] == ["claude_code"]

    # --connection prints exactly that connection's key (the projected helper).
    key = _runner.invoke(cli_app, ["provider", "key", "--connection", "agnes"])
    assert key.exit_code == 0, key.output
    assert key.output.strip() == "sk-agnes"

    # No selector → usage error.
    assert _runner.invoke(cli_app, ["provider", "key"]).exit_code == 6
