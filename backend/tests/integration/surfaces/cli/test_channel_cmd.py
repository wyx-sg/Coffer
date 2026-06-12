"""Integration tests for `coffer channel ...` subcommands (spec 009).

Same in-process daemon pattern as conftest.in_proc_daemon, but with the
channel kind + channel routes wired over a real SQLite ResourceService, a
real ChannelService/PairingManager, and a stub runtime. The CLI's HTTP
round-trips run against a Starlette TestClient via `client_or_exit`.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC
from datetime import datetime as dt
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.audit_service import AuditService
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import ChannelPeer
from coffer.application.channel.service import ChannelService
from coffer.application.resource_service import ResourceService
from coffer.domain.channel.envelopes import SentMessage
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.channel.persistence import ChannelPeerRepo
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.surfaces.cli.main import app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.channel_routes import (
    router as channel_router,
)
from coffer.surfaces.http.channel_routes import set_channel_service
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router

runner = CliRunner()
_TOKEN = "test-token-channel"

_TG_REF = "channel/tg/bot"
_ST_SECRET_REF = "channel/st/secret"
_ST_SIGNING_REF = "channel/st/signing"


class _FakeKeyring:
    """Register-time credential probe target — stored refs only."""

    def __init__(self, store: dict[str, str]) -> None:
        self._store = store

    def get(self, ref: str) -> str | None:
        return self._store.get(ref)


class _StubAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, chat_id: str, markdown: str) -> SentMessage:
        self.sent.append((chat_id, markdown))
        return SentMessage(message_id="m1")


class _StubRuntime:
    def __init__(self) -> None:
        self.adapters: dict[str, _StubAdapter] = {}
        self.listener_port = 8787
        self.listener_running = True

    def is_running(self, name: str) -> bool:
        return name in self.adapters

    def adapter(self, name: str) -> _StubAdapter | None:
        return self.adapters.get(name)


class _Daemon:
    """Handles the in-process daemon plus the loop for direct service calls."""

    def __init__(self, loop: asyncio.AbstractEventLoop, **parts: Any) -> None:
        self._loop = loop
        self.__dict__.update(parts)

    def run(self, coro: Any) -> Any:
        return self._loop.run_until_complete(coro)

    def pair(self, name: str, *, chat_id: str = "emp-1") -> None:
        resource = self.run(self.resources.get(ResourceRef(kind="channel", name=name)))
        self.run(
            self.peers.upsert(
                ChannelPeer(
                    resource_id=resource.id,
                    chat_id=chat_id,
                    display_name="Yu",
                    paired_at=dt.now(tz=UTC),
                    active_conversation_id=None,
                )
            )
        )


async def _create_tables(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def channel_daemon(tmp_path, monkeypatch):
    loop = asyncio.new_event_loop()
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    loop.run_until_complete(_create_tables(engine))
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    keyring = _FakeKeyring({_TG_REF: "raw", _ST_SECRET_REF: "raw", _ST_SIGNING_REF: "raw"})
    resources = ResourceService(
        kinds={"channel": make_channel_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        credentials=keyring,
    )
    peers = ChannelPeerRepo(sm)
    pairing = PairingManager()
    runtime = _StubRuntime()
    service = ChannelService(
        resources=resources, peers=peers, pairing=pairing, runtime=runtime, audit=audit
    )

    fapp = FastAPI()
    err_handlers.register(fapp)
    fapp.include_router(resource_router)
    fapp.include_router(channel_router)
    fapp.dependency_overrides[get_resource_service] = lambda: resources
    fapp.dependency_overrides[get_audit_service] = lambda: audit
    set_channel_service(service)
    set_active_token(_TOKEN)

    fake_client = TestClient(
        fapp,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=8000,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, info))

    yield _Daemon(loop, resources=resources, peers=peers, pairing=pairing, runtime=runtime)

    set_channel_service(None)
    set_active_token(None)
    loop.close()


def _register_tg(name: str = "tg") -> Any:
    return runner.invoke(
        app, ["channel", "register", name, "--type", "telegram", "--bot-token-ref", _TG_REF]
    )


def _register_st(name: str = "st") -> Any:
    return runner.invoke(
        app,
        [
            "channel",
            "register",
            name,
            "--type",
            "seatalk",
            "--app-id",
            "app-1",
            "--app-secret-ref",
            _ST_SECRET_REF,
            "--signing-secret-ref",
            _ST_SIGNING_REF,
        ],
    )


def _listed_names(daemon: _Daemon) -> list[str]:
    result = runner.invoke(app, ["channel", "list", "--json"])
    assert result.exit_code == 0, result.output
    return [item["name"] for item in json.loads(result.output)]


@pytest.mark.acceptance(
    spec="009-channels", scenario="register and list channels from the command line"
)
def test_register_and_list_channels(channel_daemon: _Daemon) -> None:
    r = _register_tg()
    assert r.exit_code == 0, r.output
    assert "registered: channel:tg" in r.output
    r2 = _register_st()
    assert r2.exit_code == 0, r2.output

    listed = runner.invoke(app, ["channel", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    by_name = {item["name"]: item for item in json.loads(listed.output)}
    assert by_name["tg"]["config"]["channel_type"] == "telegram"
    assert by_name["tg"]["config"]["bot_token_ref"] == _TG_REF
    assert by_name["tg"]["enabled"] is True
    assert by_name["st"]["config"]["channel_type"] == "seatalk"

    table = runner.invoke(app, ["channel", "list"])
    assert table.exit_code == 0, table.output
    assert "tg" in table.output
    assert "seatalk" in table.output


def test_register_telegram_without_token_ref_exits_6(channel_daemon: _Daemon) -> None:
    r = runner.invoke(app, ["channel", "register", "tg", "--type", "telegram"])
    assert r.exit_code == 6
    assert _listed_names(channel_daemon) == []  # nothing persisted


def test_register_seatalk_with_missing_flags_exits_6(channel_daemon: _Daemon) -> None:
    r = runner.invoke(app, ["channel", "register", "st", "--type", "seatalk", "--app-id", "app-1"])
    assert r.exit_code == 6
    assert _listed_names(channel_daemon) == []


def test_register_unknown_type_exits_6(channel_daemon: _Daemon) -> None:
    r = runner.invoke(app, ["channel", "register", "x", "--type", "discord"])
    assert r.exit_code == 6


def test_register_invalid_agent_config_json_exits_6(channel_daemon: _Daemon) -> None:
    r = runner.invoke(
        app,
        [
            "channel",
            "register",
            "tg",
            "--type",
            "telegram",
            "--bot-token-ref",
            _TG_REF,
            "--agent-config",
            "{not json",
        ],
    )
    assert r.exit_code == 6
    assert _listed_names(channel_daemon) == []


def test_register_with_missing_credential_exits_8(channel_daemon: _Daemon) -> None:
    r = runner.invoke(
        app,
        ["channel", "register", "tg", "--type", "telegram", "--bot-token-ref", "channel/absent"],
    )
    assert r.exit_code == 8  # daemon rejected with CREDENTIAL_MISSING
    assert _listed_names(channel_daemon) == []


def test_pair_prints_code_and_expiry(channel_daemon: _Daemon) -> None:
    assert _register_tg().exit_code == 0
    r = runner.invoke(app, ["channel", "pair", "tg"])
    assert r.exit_code == 0, r.output
    assert "pairing code:" in r.output
    code = r.output.split("pairing code:")[1].split()[0]
    assert len(code) == 8
    assert "expires at:" in r.output
    assert channel_daemon.pairing.pending("tg") is True


def test_pair_unknown_channel_exits_4(channel_daemon: _Daemon) -> None:
    r = runner.invoke(app, ["channel", "pair", "ghost"])
    assert r.exit_code == 4


def test_status_renders_runtime_pairing_and_callback(channel_daemon: _Daemon) -> None:
    assert _register_st().exit_code == 0
    channel_daemon.runtime.adapters["st"] = _StubAdapter()
    channel_daemon.pair("st")

    r = runner.invoke(app, ["channel", "status", "st"])
    assert r.exit_code == 0, r.output
    assert "channel:  st (seatalk)" in r.output
    assert "running: True" in r.output
    assert "no pending code" in r.output
    assert "peer:     Yu (chat emp-1)" in r.output
    assert "callback: 127.0.0.1:8787/seatalk/st (listener up)" in r.output

    as_json = runner.invoke(app, ["channel", "status", "st", "--json"])
    assert as_json.exit_code == 0, as_json.output
    body = json.loads(as_json.output)
    assert body["callback"] == {"port": 8787, "path": "/seatalk/st", "listener_running": True}


def test_status_unknown_channel_exits_4(channel_daemon: _Daemon) -> None:
    r = runner.invoke(app, ["channel", "status", "ghost"])
    assert r.exit_code == 4


def test_notify_sends_to_paired_peer(channel_daemon: _Daemon) -> None:
    assert _register_tg().exit_code == 0
    adapter = _StubAdapter()
    channel_daemon.runtime.adapters["tg"] = adapter
    channel_daemon.pair("tg", chat_id="555")

    r = runner.invoke(app, ["channel", "notify", "tg", "build green"])
    assert r.exit_code == 0, r.output
    assert "sent" in r.output
    assert adapter.sent == [("555", "build green")]


def test_notify_unpaired_channel_exits_5(channel_daemon: _Daemon) -> None:
    assert _register_tg().exit_code == 0
    channel_daemon.runtime.adapters["tg"] = _StubAdapter()
    r = runner.invoke(app, ["channel", "notify", "tg", "hello"])
    assert r.exit_code == 5  # 409 CHANNEL_NOT_PAIRED → conflict exit code
