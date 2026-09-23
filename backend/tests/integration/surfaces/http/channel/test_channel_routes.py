"""Channel routes (spec channels) over a REAL ChannelService + SQLite resources.

The router is mounted on a minimal app with the shared error handlers; the
service is wired over a real ResourceService/ChannelPeerRepo on a temp
SQLite file. Only the runtime is a stub (adapter lifecycle belongs to the
ChannelRuntime tests in the channel-core scope).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.service import ChannelService
from coffer.application.channel.store_ports import ChannelPeer
from coffer.application.resource_service import ResourceService
from coffer.domain.channel.envelopes import SentMessage
from coffer.infrastructure.channel.persistence import (
    ChannelPeerRepo,
    ChannelThreadConversationRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.channel_routes import (
    router as channel_router,
)
from coffer.surfaces.http.channel_routes import set_channel_service

_TOKEN = "test-token"
_PAIRING_ALPHABET = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
#: The agent a channel routes to, as its config now spells one: an agent UID.
#: Opaque on purpose — it is not an agent type, not an agent key and not a name,
#: and a value that looked like any of those would re-introduce the second
#: vocabulary this change removed. No agent is registered in this fixture, which
#: the channel kind reads as "registry unavailable, cannot validate" and lets
#: through; what is under test here is that the surface REPORTS the binding.
_ROUTED_AGENT_UID = "3c1d5a90b2e74f6881ac0d4e5f7b2a13"


class _StubAdapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.events: list[dict[str, Any]] = []

    async def send_text(self, chat_id: str, markdown: str) -> SentMessage:
        self.sent.append((chat_id, markdown))
        return SentMessage(message_id="m1")

    async def handle_event(self, envelope: dict[str, Any]) -> None:
        self.events.append(envelope)


class _StubRuntime:
    def __init__(self) -> None:
        self.adapters: dict[str, _StubAdapter] = {}
        self.listener_port = 8787
        self.listener_running = True

    def is_running(self, name: str) -> bool:
        return name in self.adapters

    def tunnel_running(self, name: str) -> bool:
        return False

    def adapter(self, name: str) -> _StubAdapter | None:
        return self.adapters.get(name)

    async def local_machine_id(self) -> str | None:
        # This stub stands in for a runtime that was never given a machine, so
        # the binding gate is skipped for it and every channel reads as local —
        # which is what these route tests are about, not the binding.
        return None


@dataclass
class _Ctx:
    app: FastAPI
    runtime: _StubRuntime
    peers: ChannelPeerRepo
    threads: ChannelThreadConversationRepo
    pairing: PairingManager
    resources: ResourceService
    # The two identities the routes take. The integer ids beside them are the
    # surrogate PK the peer/thread tables hold — internal, never on the wire —
    # so both spellings are kept: a test pairs by ``*_id`` and calls by ``*_uid``.
    tg_uid: str = ""
    st_uid: str = ""
    tg_id: int = 0
    st_id: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
async def ctx(tmp_path) -> AsyncIterator[_Ctx]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"channel": make_channel_kind()}, repo=SqlAlchemyResourceRepo(sm), audit=audit
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

    tg = await resources.register(
        "channel",
        "tg",
        {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot"},
        actor="test",
    )
    st = await resources.register(
        "channel",
        "st",
        {
            "channel_type": "seatalk",
            "app_id": "app-1",
            "app_secret_ref": "channel/st/secret",
            "signing_secret_ref": "channel/st/signing",
        },
        actor="test",
    )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(channel_router)
    set_channel_service(service)
    set_active_token(_TOKEN)
    yield _Ctx(
        app=app,
        runtime=runtime,
        peers=peers,
        threads=threads,
        pairing=pairing,
        resources=resources,
        tg_uid=tg.uid,
        st_uid=st.uid,
        tg_id=tg.id,
        st_id=st.id,
    )
    set_channel_service(None)
    set_active_token(None)
    await engine.dispose()


def _client(app: FastAPI, *, token: str | None = _TOKEN) -> AsyncClient:
    headers = {"X-Coffer-Token": token} if token is not None else {}
    return AsyncClient(transport=ASGITransport(app), base_url="http://t", headers=headers)


async def _pair(ctx: _Ctx, resource_id: int, *, chat_id: str = "emp-1") -> None:
    await ctx.peers.upsert(
        ChannelPeer(
            resource_id=resource_id,
            chat_id=chat_id,
            display_name="Yu",
            paired_at=datetime.now(tz=UTC),
        )
    )
    # The conversation pointer lives on the DM's thread row, not on the peer.
    await ctx.threads.set_active_conversation(resource_id, chat_id, "", "conv-9")


async def test_channel_routes_require_token(ctx: _Ctx) -> None:
    async with _client(ctx.app, token=None) as c:
        r = await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_unknown_channel_is_404_on_every_route(ctx: _Ctx) -> None:
    requests = [
        ("GET", "/api/v1/channels/nope/status", None),
        ("POST", "/api/v1/channels/nope/pairing-code", None),
        ("POST", "/api/v1/channels/nope/notify", {"text": "hi"}),
        ("POST", "/api/v1/channels/nope/events", {"event_type": "x", "event": {}}),
    ]
    async with _client(ctx.app) as c:
        for method, path, body in requests:
            r = await c.request(method, path, json=body)
            assert r.status_code == 404, (method, path, r.text)
            assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_pairing_code_returns_8_char_code_with_expiry(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/pairing-code")
    assert r.status_code == 200
    body = r.json()
    assert len(body["code"]) == 8
    assert set(body["code"]) <= _PAIRING_ALPHABET  # unambiguous alphabet only
    expires = datetime.fromisoformat(body["expires_at"])
    assert expires > datetime.now(tz=UTC)
    assert ctx.pairing.pending("tg") is True  # the service's manager holds the code


async def test_status_telegram_defaults(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")
    assert r.status_code == 200
    assert r.json() == {
        # Both travel: the uid is what a surface addresses the channel by, the
        # name is what it shows. A status that carried only the label would
        # leave every client that has to call back needing a second lookup.
        "uid": ctx.tg_uid,
        "name": "tg",
        "channel_type": "telegram",
        "enabled": True,
        "running": False,
        "pending_pairing": False,
        "peer": None,
        "callback": None,  # telegram needs no callback ingress
        "diagnostics": [],  # nothing contradicts the configuration
        # The binding travels on the wire even when there is nothing to say:
        # a surface must be able to tell "bound elsewhere" from "stopped", and
        # a field that appeared only sometimes would make that a guess.
        "runs_on": None,
        "runs_here": True,  # this runtime has no machine, so nothing is foreign
    }


@pytest.mark.acceptance(
    spec="channels",
    scenario="channel status reports runtime, pairing, and callback details",
)
async def test_status_reports_runtime_pairing_and_callback_details(ctx: _Ctx) -> None:
    ctx.runtime.adapters["st"] = _StubAdapter()
    await _pair(ctx, ctx.st_id)
    async with _client(ctx.app) as c:
        issued = await c.post(f"/api/v1/channels/{ctx.st_uid}/pairing-code")
        assert issued.status_code == 200
        r = await c.get(f"/api/v1/channels/{ctx.st_uid}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["uid"] == ctx.st_uid
    assert body["name"] == "st"
    assert body["channel_type"] == "seatalk"
    assert body["enabled"] is True
    assert body["running"] is True  # adapter live in the runtime
    assert body["pending_pairing"] is True  # unexpired code outstanding
    assert body["peer"]["chat_id"] == "emp-1"
    assert body["peer"]["display_name"] == "Yu"
    assert body["peer"]["active_conversation_id"] == "conv-9"
    assert body["callback"] == {
        "delivery": "webhook",
        "port": 8787,
        # The public callback path spells the UID. It is registered by hand on
        # SeaTalk's portal and never re-read, so the one thing it may not
        # contain is a label the owner is invited to change (``callback_path``).
        "path": f"/seatalk/{ctx.st_uid}",
        "listener_running": True,
        "public_base_url": None,
        "public_callback_url": None,
        "tunnel_managed": False,
        "tunnel_running": False,
        "websocket_state": None,
        "websocket_error": None,
    }


@pytest.mark.acceptance(
    spec="channels",
    scenario=(
        "the management surface lists each Coffer-hosted channel "
        "with status, owner, agent, and health"
    ),
)
async def test_management_surface_reports_status_owner_agent_and_health(ctx: _Ctx) -> None:
    # A registered + running Coffer-hosted channel, bound to an agent and paired
    # with an owner. The management surface = the resource list (kind=channel,
    # carrying enabled + the routed agent) plus the per-channel status endpoint
    # (live health + paired owner). "List every Coffer-hosted channel on one
    # management surface": it must report all four.
    mg = await ctx.resources.register(
        "channel",
        "mg",
        {
            "channel_type": "telegram",
            "bot_token_ref": "channel/mg/bot",
            "default_agent": _ROUTED_AGENT_UID,
        },
        actor="test",
    )
    ctx.runtime.adapters["mg"] = _StubAdapter()  # adapter live -> healthy
    await _pair(ctx, mg.id)

    # The list view mirrors the MCP-server/memory/skill surfaces: each row is a
    # resource carrying its enabled status and the routed agent.
    listed = {r.name: r for r in await ctx.resources.list(kind="channel")}
    assert "mg" in listed
    assert listed["mg"].enabled is True  # status
    assert listed["mg"].config["default_agent"] == _ROUTED_AGENT_UID  # agent

    # The per-channel status supplies the live health + paired owner.
    async with _client(ctx.app) as c:
        r = await c.get(f"/api/v1/channels/{mg.uid}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True  # status
    assert body["running"] is True  # health — adapter live in the runtime
    assert body["peer"]["display_name"] == "Yu"  # paired owner
    assert body["peer"]["chat_id"] == "emp-1"


async def test_notify_delivers_to_paired_peer(ctx: _Ctx) -> None:
    adapter = _StubAdapter()
    ctx.runtime.adapters["tg"] = adapter
    await _pair(ctx, ctx.tg_id, chat_id="555")
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/notify", json={"text": "build green"})
    assert r.status_code == 200
    assert r.json() == {"sent": True}
    assert adapter.sent == [("555", "build green")]


async def test_notify_unpaired_channel_is_409(ctx: _Ctx) -> None:
    ctx.runtime.adapters["tg"] = _StubAdapter()
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/notify", json={"text": "hi"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CHANNEL_NOT_PAIRED"


async def test_notify_with_adapter_down_is_409(ctx: _Ctx) -> None:
    await _pair(ctx, ctx.tg_id)  # paired, but no adapter running
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/notify", json={"text": "hi"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CHANNEL_NOT_RUNNING"


async def test_notify_rejects_empty_text(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/notify", json={"text": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CONFIG_INVALID"


async def test_events_ingest_reaches_the_adapter(ctx: _Ctx) -> None:
    adapter = _StubAdapter()
    ctx.runtime.adapters["st"] = adapter
    envelope = {
        "event_type": "message_from_bot_subscriber",
        "timestamp": 1718000000,
        "event": {"employee_code": "emp-1", "message": {"tag": "text", "text": {"content": "hi"}}},
    }
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.st_uid}/events", json=envelope)
    assert r.status_code == 200
    assert r.json() == {"accepted": True}
    # Processing is scheduled in the background so the listener's tight
    # forward timeout is never blocked by outbound platform calls.
    for _ in range(100):
        if adapter.events:
            break
        await asyncio.sleep(0.01)
    assert adapter.events == [envelope]  # the raw envelope reached handle_event


async def test_events_with_adapter_down_is_409(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.post(
            f"/api/v1/channels/{ctx.st_uid}/events", json={"event_type": "x", "event": {}}
        )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CHANNEL_NOT_RUNNING"
