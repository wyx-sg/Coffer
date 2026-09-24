"""Integration tests for `coffer channel ...` subcommands (spec channels).

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
from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.service import ChannelService
from coffer.application.channel.store_ports import ChannelPeer
from coffer.application.resource_service import ResourceService
from coffer.domain.channel.envelopes import SentMessage
from coffer.domain.scope import Scope
from coffer.infrastructure.channel.persistence import (
    ChannelPeerRepo,
    ChannelThreadConversationRepo,
)
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

#: The one registered agent every channel here is bound to, as a person names
#: it. What gets STORED is its uid — the CLI resolves the name once, which is
#: the whole of what ``--agent`` does.
_AGENT_NAME = "claude-code"


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


#: The id the stubbed ``/daemon/status`` answers with, so the CLI binds a freshly
#: registered channel to "this machine" the way it does against a real daemon.
_MACHINE_ID = "0123456789abcdef"


class _StubRuntime:
    def __init__(self) -> None:
        self.adapters: dict[str, _StubAdapter] = {}
        #: channel UID -> (state, last error), as ``ChannelRuntime.websocket_state``
        #: answers for a SeaTalk channel. Keyed by uid and
        #: not by name, because the real websocket controller is: the
        #: connection's own key is the channel's uid, so a rename does not drop
        #: a live connection on the floor.
        self.websocket_states: dict[str, str] = {}
        self.websocket_errors: dict[str, str] = {}

    def websocket_state(self, channel_uid: str) -> tuple[str, str | None] | None:
        state = self.websocket_states.get(channel_uid)
        if state is None:
            return None
        return state, self.websocket_errors.get(channel_uid)

    def is_running(self, name: str) -> bool:
        return name in self.adapters

    async def local_machine_id(self) -> str:
        return _MACHINE_ID

    def adapter(self, name: str) -> _StubAdapter | None:
        return self.adapters.get(name)


class _Daemon:
    """Handles the in-process daemon plus the loop for direct service calls."""

    def __init__(self, loop: asyncio.AbstractEventLoop, **parts: Any) -> None:
        self._loop = loop
        self.__dict__.update(parts)

    def run(self, coro: Any) -> Any:
        return self._loop.run_until_complete(coro)

    def channel(self, name: str) -> Any:
        """The channel row behind a name a test typed.

        ``get_by_name`` and not ``get``: a uid addresses a resource everywhere
        inside the daemon now (ADR resource-identity-is-an-immutable-uid), and
        a test standing where a person stands holds the label — so it resolves
        it the same way the CLI does, once, at the edge.
        """
        return self.run(self.resources.get_by_name("channel", name))

    def uid(self, name: str) -> str:
        """A channel's uid, which every runtime key and every route now takes."""
        return str(self.channel(name).uid)

    def pair(self, name: str, *, chat_id: str = "emp-1") -> None:
        resource = self.channel(name)
        self.run(
            self.peers.upsert(
                ChannelPeer(
                    resource_id=resource.id,
                    chat_id=chat_id,
                    display_name="Yu",
                    paired_at=dt.now(tz=UTC),
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
    keyring = _FakeKeyring({_TG_REF: "raw", _ST_SECRET_REF: "raw"})

    async def _agent_names() -> dict[str, str]:
        return {a.uid: a.name for a in await resources.list(kind="agent")}

    resources = ResourceService(
        # The `agent` kind is wired in as well, which it did not need to be
        # before: a channel's ``default_agent`` holds an agent UID
        # (ADR resource-identity-is-an-immutable-uid), so `coffer channel
        # register --agent <name>` has a name to resolve and the kind's own
        # "is that a registered agent" check has a registry to ask.
        kinds={"channel": make_channel_kind(agent_names=_agent_names), "agent": make_agent_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        credentials=keyring,
    )
    # Registered through the service because the agent kind refuses the generic
    # create path. One agent is enough: every command here binds to the same one.
    agent = loop.run_until_complete(
        resources.register(
            kind="agent",
            name=_AGENT_NAME,
            config={"type": "claude_code", "config_dir": str(tmp_path / _AGENT_NAME)},
            actor="test",
            allow_lifecycle_kind=True,
        )
    )
    peers = ChannelPeerRepo(sm)
    threads = ChannelThreadConversationRepo(sm)
    pairing = PairingManager()
    runtime = _StubRuntime()
    service = ChannelService(
        resources=resources,
        peers=peers,
        threads=threads,
        pairing=pairing,
        runtime=runtime,
        audit=audit,
    )

    fapp = FastAPI()
    err_handlers.register(fapp)
    fapp.include_router(resource_router)
    fapp.include_router(channel_router)

    # `coffer channel register` and `coffer channel bind` ask the daemon which
    # machine it is, because a CLI deriving its own id would be a second answer
    # to a question that must have exactly one. The real daemon always serves
    # this; the stub serves the one field they read.
    @fapp.get("/api/v1/daemon/status")
    def _daemon_status() -> dict[str, Any]:
        return {"machine_id": _MACHINE_ID}

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

    yield _Daemon(
        loop,
        resources=resources,
        peers=peers,
        pairing=pairing,
        runtime=runtime,
        agent_uid=agent.uid,
    )

    set_channel_service(None)
    set_active_token(None)
    loop.close()


def _register_tg(name: str = "tg") -> Any:
    # ``--agent`` is required, not defaulted: a uid is minted per vault, so no
    # constant can stand for "the usual agent" and a channel bound to nobody
    # would simply route nowhere.
    return runner.invoke(
        app,
        [
            "channel",
            "register",
            name,
            "--type",
            "telegram",
            "--bot-token-ref",
            _TG_REF,
            "--agent",
            _AGENT_NAME,
        ],
    )


def _register_st(name: str = "st") -> Any:
    argv = [
        "channel",
        "register",
        name,
        "--type",
        "seatalk",
        "--app-id",
        "app-1",
        "--app-secret-ref",
        _ST_SECRET_REF,
        "--agent",
        _AGENT_NAME,
    ]
    return runner.invoke(app, argv)


def _listed_names(daemon: _Daemon) -> list[str]:
    result = runner.invoke(app, ["channel", "list", "--json"])
    assert result.exit_code == 0, result.output
    return [item["name"] for item in json.loads(result.output)]


@pytest.mark.acceptance(
    spec="channels", scenario="register and list channels from the command line"
)
def test_register_and_list_channels(channel_daemon: _Daemon) -> None:
    r = _register_tg()
    assert r.exit_code == 0, r.output
    assert "registered: channel tg" in r.output
    r2 = _register_st()
    assert r2.exit_code == 0, r2.output

    listed = runner.invoke(app, ["channel", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    by_name = {item["name"]: item for item in json.loads(listed.output)}
    assert by_name["tg"]["config"]["channel_type"] == "telegram"
    assert by_name["tg"]["config"]["bot_token_ref"] == _TG_REF
    # The agent NAME the user typed was resolved to the agent's uid before it
    # was stored, so renaming the agent later cannot unbind the channel.
    assert by_name["tg"]["config"]["default_agent"] == channel_daemon.agent_uid
    assert by_name["tg"]["enabled"] is True
    assert by_name["st"]["config"]["channel_type"] == "seatalk"

    table = runner.invoke(app, ["channel", "list"])
    assert table.exit_code == 0, table.output
    assert "tg" in table.output
    assert "seatalk" in table.output


def test_register_carries_no_scope(channel_daemon: _Daemon) -> None:
    """A channel declares no activation scope (ADR per-agent-resource-scope) —
    registration writes none, so a newly registered channel may drive every
    registered agent until the owner narrows it.

    Its machine BINDING is a different field and registration does write that
    one: an unbound channel runs nowhere, so leaving it out would make the
    plain registration produce a bot that never answers."""
    r = _register_tg()
    assert r.exit_code == 0, r.output
    resource = channel_daemon.channel("tg")
    assert resource.scope is None
    assert resource.config["runs_on"] == _MACHINE_ID


def test_bind_moves_the_channel_to_another_machine_and_keeps_the_rest(
    channel_daemon: _Daemon,
) -> None:
    """`coffer channel bind` is an ordinary config edit, and must stay one.

    The credential refs are the thing to watch: a bind that rebuilt the config
    from flags instead of patching the stored one would drop them, and the
    channel would arrive on its new machine with no way to authenticate.
    """
    assert _register_tg().exit_code == 0

    result = runner.invoke(app, ["channel", "bind", "tg", "ffffffffffffffff"])
    assert result.exit_code == 0, result.output

    resource = channel_daemon.channel("tg")
    assert resource.config["runs_on"] == "ffffffffffffffff"
    assert resource.config["bot_token_ref"] == _TG_REF
    # Same reason as the credential refs, and a harder one to spot: the bound
    # agent is stored as a uid, and a rebuilt config would lose it silently.
    assert resource.config["default_agent"] == channel_daemon.agent_uid

    # With no machine named, bind takes the daemon it is talking to.
    assert runner.invoke(app, ["channel", "bind", "tg"]).exit_code == 0
    resource = channel_daemon.channel("tg")
    assert resource.config["runs_on"] == _MACHINE_ID


@pytest.mark.acceptance(
    spec="channels",
    scenario="a channel may only route to the agents in its scope",
)
def test_scope_set_on_a_channel_narrows_the_agents_it_may_drive(
    channel_daemon: _Daemon,
) -> None:
    """`coffer scope set channel <name>` names the agents this channel may
    route to (ADR per-agent-resource-scope). It is the same framework surface every scoped
    kind shares — the channel kind no longer refuses it.

    The CLI takes the agent's NAME and what lands in the row is its UID: the
    scope and the channel's ``default_agent`` are written in the same
    vocabulary, which is what lets the kind hold one inside the other by
    comparing them directly."""
    assert _register_tg().exit_code == 0

    result = runner.invoke(app, ["scope", "set", "channel", "tg", "--agents", _AGENT_NAME])

    assert result.exit_code == 0, result.output
    resource = channel_daemon.channel("tg")
    assert resource.scope == Scope(agents=[channel_daemon.agent_uid])


def test_register_telegram_without_token_ref_exits_6(channel_daemon: _Daemon) -> None:
    r = runner.invoke(
        app, ["channel", "register", "tg", "--type", "telegram", "--agent", _AGENT_NAME]
    )
    assert r.exit_code == 6
    assert _listed_names(channel_daemon) == []  # nothing persisted


def test_register_seatalk_with_missing_flags_exits_6(channel_daemon: _Daemon) -> None:
    r = runner.invoke(
        app,
        [
            "channel",
            "register",
            "st",
            "--type",
            "seatalk",
            "--app-id",
            "app-1",
            "--agent",
            _AGENT_NAME,
        ],
    )
    assert r.exit_code == 6
    assert _listed_names(channel_daemon) == []


def test_register_unknown_type_exits_6(channel_daemon: _Daemon) -> None:
    r = runner.invoke(
        app, ["channel", "register", "x", "--type", "discord", "--agent", _AGENT_NAME]
    )
    assert r.exit_code == 6


def test_register_without_an_agent_is_refused(channel_daemon: _Daemon) -> None:
    """``--agent`` carries no default, so leaving it out is a usage error and
    not a channel quietly bound to a name nothing was ever registered under.

    Typer's own missing-required-option exit (2), not one of the CLI's codes:
    the command never runs, which is the point — the refusal happens before
    anything reaches the daemon."""
    r = runner.invoke(
        app, ["channel", "register", "tg", "--type", "telegram", "--bot-token-ref", _TG_REF]
    )
    assert r.exit_code == 2
    assert _listed_names(channel_daemon) == []


def test_register_with_an_unknown_agent_exits_4(channel_daemon: _Daemon) -> None:
    """The name is resolved to a uid before the channel is written, so an agent
    this vault does not hold is caught at the surface the user typed at rather
    than stored as a binding that drives nothing."""
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
            "--agent",
            "ghost",
        ],
    )
    assert r.exit_code == 4
    assert _listed_names(channel_daemon) == []


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
            "--agent",
            _AGENT_NAME,
            "--agent-config",
            "{not json",
        ],
    )
    assert r.exit_code == 6
    assert _listed_names(channel_daemon) == []


def test_register_with_missing_credential_exits_8(channel_daemon: _Daemon) -> None:
    r = runner.invoke(
        app,
        [
            "channel",
            "register",
            "tg",
            "--type",
            "telegram",
            "--bot-token-ref",
            "channel/absent",
            "--agent",
            _AGENT_NAME,
        ],
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


def test_status_renders_runtime_pairing_and_inbound(channel_daemon: _Daemon) -> None:
    assert _register_st().exit_code == 0
    channel_daemon.runtime.adapters["st"] = _StubAdapter()
    channel_daemon.pair("st")

    r = runner.invoke(app, ["channel", "status", "st"])
    assert r.exit_code == 0, r.output
    assert "channel:  st (seatalk)" in r.output
    assert "running: True" in r.output
    assert "no pending code" in r.output
    assert "peer:     Yu (chat emp-1)" in r.output
    # No connection attempt yet: said as such, not as a fault.
    assert "inbound:  websocket (not connected yet)" in r.output

    as_json = runner.invoke(app, ["channel", "status", "st", "--json"])
    assert as_json.exit_code == 0, as_json.output
    body = json.loads(as_json.output)
    assert body["inbound"] == {"websocket_state": None, "websocket_error": None}
    assert "callback" not in body


def test_register_seatalk_takes_no_inbound_transport_option(channel_daemon: _Daemon) -> None:
    """The SeaTalk channel is its app credentials: there is no delivery choice,
    signing secret, public URL or tunnel token to give it."""
    for flag, value in (
        ("--delivery", "webhook"),
        ("--signing-secret-ref", "channel/st/signing"),
    ):
        r = runner.invoke(
            app,
            [
                "channel",
                "register",
                "st",
                "--type",
                "seatalk",
                "--app-id",
                "app-1",
                "--app-secret-ref",
                _ST_SECRET_REF,
                "--agent",
                _AGENT_NAME,
                flag,
                value,
            ],
        )
        assert r.exit_code != 0
    assert _listed_names(channel_daemon) == []
    assert _register_st().exit_code == 0
    config = channel_daemon.channel("st").config
    for key in ("delivery", "signing_secret_ref", "public_base_url", "tunnel_token_ref"):
        assert key not in config


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="status names the websocket connection state",
)
def test_status_names_the_websocket_connection_state(channel_daemon: _Daemon) -> None:
    """Spec channels/seatalk "Report the websocket connection as the channel's
    inbound state": one channel connected, one whose last attempt failed, read
    through the REST body (``--json`` is the route's own answer) and the CLI's
    rendering of it. Neither surface names a listener, port, path, URL or tunnel.
    """
    assert _register_st("up").exit_code == 0
    assert _register_st("down").exit_code == 0
    for name in ("up", "down"):
        channel_daemon.runtime.adapters[name] = _StubAdapter()
    channel_daemon.runtime.websocket_states[channel_daemon.uid("up")] = "connected"
    down = channel_daemon.uid("down")
    channel_daemon.runtime.websocket_states[down] = "error"
    channel_daemon.runtime.websocket_errors[down] = "register handshake refused: bad app secret"

    up_text = runner.invoke(app, ["channel", "status", "up"])
    down_text = runner.invoke(app, ["channel", "status", "down"])
    assert up_text.exit_code == 0 and down_text.exit_code == 0
    assert "inbound:  websocket (connected)" in up_text.output
    assert "ws error" not in up_text.output
    assert "inbound:  websocket (error)" in down_text.output
    assert "ws error: register handshake refused: bad app secret" in down_text.output

    up_json = json.loads(runner.invoke(app, ["channel", "status", "up", "--json"]).output)
    down_json = json.loads(runner.invoke(app, ["channel", "status", "down", "--json"]).output)
    assert up_json["inbound"] == {"websocket_state": "connected", "websocket_error": None}
    assert down_json["inbound"] == {
        "websocket_state": "error",
        "websocket_error": "register handshake refused: bad app secret",
    }

    for rendered in (up_text.output, down_text.output):
        for word in ("listener", "127.0.0.1", "/seatalk/", "tunnel", "https://"):
            assert word not in rendered
    for body in (up_json, down_json):
        assert set(body["inbound"]) == {"websocket_state", "websocket_error"}
        assert "callback" not in body


def test_status_of_a_websocket_channel_prints_its_error_verbatim(
    channel_daemon: _Daemon,
) -> None:
    """The two websocket failures that matter — no SDK installed, another
    process already holding the connection — are only actionable if the owner
    can read them."""
    assert _register_st().exit_code == 0
    channel_daemon.runtime.adapters["st"] = _StubAdapter()
    st_uid = channel_daemon.uid("st")
    channel_daemon.runtime.websocket_states[st_uid] = "kicked"
    channel_daemon.runtime.websocket_errors[st_uid] = "another connection took over"

    r = runner.invoke(app, ["channel", "status", "st"])
    assert r.exit_code == 0, r.output
    assert "inbound:  websocket (kicked)" in r.output
    assert "ws error: another connection took over" in r.output


def test_status_says_an_unbound_channel_runs_nowhere(channel_daemon: _Daemon) -> None:
    """Spec channels "Bind each channel to the one machine that runs it": unbound
    must be reported as itself, never looking like the normal state of a channel
    that another machine runs."""
    assert _register_tg().exit_code == 0
    resource = channel_daemon.channel("tg")
    config = {k: v for k, v in resource.config.items() if k != "runs_on"}
    channel_daemon.run(channel_daemon.resources.update_config(resource.uid, config, "test"))

    r = runner.invoke(app, ["channel", "status", "tg"])
    assert r.exit_code == 0, r.output
    assert "runs on:  unbound (runs nowhere)" in r.output
    assert "another machine" not in r.output


def test_status_names_the_foreign_machine_a_bound_channel_runs_on(
    channel_daemon: _Daemon,
) -> None:
    assert _register_tg().exit_code == 0
    assert runner.invoke(app, ["channel", "bind", "tg", "ffffffffffffffff"]).exit_code == 0

    r = runner.invoke(app, ["channel", "status", "tg"])
    assert r.exit_code == 0, r.output
    assert "runs on:  ffffffffffffffff (another machine)" in r.output

    assert runner.invoke(app, ["channel", "bind", "tg"]).exit_code == 0
    r = runner.invoke(app, ["channel", "status", "tg"])
    assert f"runs on:  {_MACHINE_ID} (this machine)" in r.output


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
