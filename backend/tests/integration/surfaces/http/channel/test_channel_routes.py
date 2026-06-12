"""Channel routes (spec 009) over a REAL ChannelService + SQLite resources.

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
from coffer.application.channel.ports import ChannelPeer
from coffer.application.channel.service import ChannelService
from coffer.application.resource_service import ResourceService
from coffer.domain.channel.envelopes import SentMessage
from coffer.infrastructure.channel.persistence import ChannelPeerRepo
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

    def adapter(self, name: str) -> _StubAdapter | None:
        return self.adapters.get(name)


@dataclass
class _Ctx:
    app: FastAPI
    runtime: _StubRuntime
    peers: ChannelPeerRepo
    pairing: PairingManager
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
    pairing = PairingManager()
    runtime = _StubRuntime()
    service = ChannelService(
        resources=resources, peers=peers, pairing=pairing, runtime=runtime, audit=audit
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
    yield _Ctx(app=app, runtime=runtime, peers=peers, pairing=pairing, tg_id=tg.id, st_id=st.id)
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
            active_conversation_id="conv-9",
        )
    )


async def test_channel_routes_require_token(ctx: _Ctx) -> None:
    async with _client(ctx.app, token=None) as c:
        r = await c.get("/api/v1/channels/tg/status")
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
        r = await c.post("/api/v1/channels/tg/pairing-code")
    assert r.status_code == 200
    body = r.json()
    assert len(body["code"]) == 8
    assert set(body["code"]) <= _PAIRING_ALPHABET  # unambiguous alphabet only
    expires = datetime.fromisoformat(body["expires_at"])
    assert expires > datetime.now(tz=UTC)
    assert ctx.pairing.pending("tg") is True  # the service's manager holds the code


async def test_status_telegram_defaults(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.get("/api/v1/channels/tg/status")
    assert r.status_code == 200
    assert r.json() == {
        "name": "tg",
        "channel_type": "telegram",
        "enabled": True,
        "running": False,
        "pending_pairing": False,
        "peer": None,
        "callback": None,  # telegram needs no callback ingress
    }


@pytest.mark.acceptance(
    spec="009-channels",
    scenario="channel status reports runtime, pairing, and callback details",
)
async def test_status_reports_runtime_pairing_and_callback_details(ctx: _Ctx) -> None:
    ctx.runtime.adapters["st"] = _StubAdapter()
    await _pair(ctx, ctx.st_id)
    async with _client(ctx.app) as c:
        issued = await c.post("/api/v1/channels/st/pairing-code")
        assert issued.status_code == 200
        r = await c.get("/api/v1/channels/st/status")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "st"
    assert body["channel_type"] == "seatalk"
    assert body["enabled"] is True
    assert body["running"] is True  # adapter live in the runtime
    assert body["pending_pairing"] is True  # unexpired code outstanding
    assert body["peer"]["chat_id"] == "emp-1"
    assert body["peer"]["display_name"] == "Yu"
    assert body["peer"]["active_conversation_id"] == "conv-9"
    assert body["callback"] == {"port": 8787, "path": "/seatalk/st", "listener_running": True}


async def test_notify_delivers_to_paired_peer(ctx: _Ctx) -> None:
    adapter = _StubAdapter()
    ctx.runtime.adapters["tg"] = adapter
    await _pair(ctx, ctx.tg_id, chat_id="555")
    async with _client(ctx.app) as c:
        r = await c.post("/api/v1/channels/tg/notify", json={"text": "build green"})
    assert r.status_code == 200
    assert r.json() == {"sent": True}
    assert adapter.sent == [("555", "build green")]


async def test_notify_unpaired_channel_is_409(ctx: _Ctx) -> None:
    ctx.runtime.adapters["tg"] = _StubAdapter()
    async with _client(ctx.app) as c:
        r = await c.post("/api/v1/channels/tg/notify", json={"text": "hi"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CHANNEL_NOT_PAIRED"


async def test_notify_with_adapter_down_is_409(ctx: _Ctx) -> None:
    await _pair(ctx, ctx.tg_id)  # paired, but no adapter running
    async with _client(ctx.app) as c:
        r = await c.post("/api/v1/channels/tg/notify", json={"text": "hi"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CHANNEL_NOT_RUNNING"


async def test_notify_rejects_empty_text(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.post("/api/v1/channels/tg/notify", json={"text": ""})
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
        r = await c.post("/api/v1/channels/st/events", json=envelope)
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
        r = await c.post("/api/v1/channels/st/events", json={"event_type": "x", "event": {}})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CHANNEL_NOT_RUNNING"
