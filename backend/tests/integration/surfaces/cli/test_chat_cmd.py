"""CLI coverage for `coffer chat ...` (spec 008-builtin-agent-chat).

Wires a chat-enabled in-process daemon (chat router + ChatService over SQLite
with a FakeRuntimeFactory) and drives the Typer app through CliRunner.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime as dt

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.application.audit_service import AuditService
from coffer.application.builtin_agent.kind import (
    ensure_default_builtin_agent,
    make_builtin_agent_kind,
)
from coffer.application.chat.service import ChatService
from coffer.application.resource_service import ResourceService
from coffer.domain.chat.runtime import TextDelta, ToolCallStarted, ToolResultEvent
from coffer.domain.resource import Kind
from coffer.infrastructure.chat.persistence import (
    SqlAlchemyConversationRepo,
    SqlAlchemyMessageRepo,
)
from coffer.infrastructure.daemon.pid_lock import DaemonInfo, write
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.cli import main
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.routes import router as chat_router
from coffer.surfaces.http.dependencies import get_chat_service
from tests.integration.chat.fakes import FakeRuntime, FakeRuntimeFactory

_TOKEN = "test-token"


@dataclass
class ChatCli:
    factory: FakeRuntimeFactory
    home: object


@pytest.fixture
def chat_cli(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    loop = asyncio.new_event_loop()

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = session_maker(engine)
        audit = AuditService(SqlAlchemyAuditRepo(sm))
        kinds: dict[str, Kind] = {"builtin_agent": make_builtin_agent_kind(on_delete=None)}
        resources = ResourceService(kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
        await ensure_default_builtin_agent(resources)
        factory = FakeRuntimeFactory()
        chat = ChatService(
            conversations=SqlAlchemyConversationRepo(sm),
            messages=SqlAlchemyMessageRepo(sm),
            resources=resources,
            runtime_factory=factory,
            audit=audit,
        )
        return chat, factory

    chat_svc, factory = loop.run_until_complete(_setup())

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(chat_router)
    app.dependency_overrides[get_chat_service] = lambda: chat_svc
    set_active_token(_TOKEN)

    daemon_dir = home / ".coffer"
    daemon_dir.mkdir(parents=True, exist_ok=True)
    info = DaemonInfo(
        version=1, pid=123, port=8000, token=_TOKEN, started_at=dt.now(tz=UTC), binary_path="/t"
    )
    write(daemon_dir / "daemon.json", info)
    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )
    from coffer.surfaces.cli import _client as _cli_client

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, info))
    try:
        yield ChatCli(factory=factory, home=home)
    finally:
        set_active_token(None)
        loop.run_until_complete(engine.dispose())
        loop.close()


def _run(args: list[str], **kw):
    return CliRunner().invoke(main.app, args, **kw)


def test_new_prints_conversation_id(chat_cli):
    res = _run(["chat", "new"])
    assert res.exit_code == 0, res.output
    cid = res.output.strip()
    assert cid
    # The conversation is listed.
    res = _run(["chat", "list", "--json"])
    assert res.exit_code == 0
    assert cid in res.output


def test_send_streams_reply_to_stdout(chat_cli):
    chat_cli.factory.runtime = FakeRuntime(
        [
            ToolCallStarted(id="t1", tool="coffer__list_mcp_servers", args={}),
            ToolResultEvent(id="t1", tool="coffer__list_mcp_servers", ok=True, summary="ok"),
            TextDelta(text="Hello from the agent"),
        ]
    )
    cid = _run(["chat", "new"]).output.strip()
    res = _run(["chat", "send", cid, "hi there"])
    assert res.exit_code == 0, res.output
    assert "Hello from the agent" in res.output
    # History reflects the exchange.
    show = _run(["chat", "show", cid, "--json"])
    assert "hi there" in show.output
    assert "Hello from the agent" in show.output


def test_rename_archive_restore_delete(chat_cli):
    cid = _run(["chat", "new"]).output.strip()
    assert _run(["chat", "rename", cid, "My chat"]).exit_code == 0
    assert _run(["chat", "archive", cid]).exit_code == 0
    assert _run(["chat", "restore", cid]).exit_code == 0
    res = _run(["chat", "rm", cid, "--force"])
    assert res.exit_code == 0
    # Gone now -> show fails (404 -> non-zero exit).
    assert _run(["chat", "show", cid]).exit_code != 0


def test_show_renders_history(chat_cli):
    chat_cli.factory.runtime = FakeRuntime([TextDelta(text="answer")])
    cid = _run(["chat", "new"]).output.strip()
    _run(["chat", "send", cid, "question"])
    res = _run(["chat", "show", cid])
    assert res.exit_code == 0
    assert "[user] question" in res.output
    assert "[assistant] answer" in res.output
