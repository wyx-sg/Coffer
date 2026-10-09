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
from coffer.application.channel.avatars import PersonAvatars
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.service import ChannelService
from coffer.application.channel.store_ports import ChannelPeer
from coffer.application.resource_service import ResourceService
from coffer.domain.channel.envelopes import SentMessage
from coffer.domain.channel.errors import ChannelNotRunning
from coffer.infrastructure.channel.avatar_store import FileAvatarStore
from coffer.infrastructure.channel.persistence import (
    ChannelPeerRepo,
    ChannelThreadConversationRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.vault.home import content_root
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.channel_routes import (
    get_channel_service,
    set_channel_avatars,
    set_channel_service,
)
from coffer.surfaces.http.channel_routes import (
    router as channel_router,
)
from tests.support.vault_stores import make_resource_repo

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
        #: channel uid -> (websocket state, last error)
        self.websockets: dict[str, tuple[str, str | None]] = {}
        self.restarted: list[str] = []
        #: channel uid -> "pending" | "refused"
        self.withheld: dict[str, str] = {}

    def secret_withheld(self, channel_uid: str) -> str | None:
        return self.withheld.get(channel_uid)

    async def restart(self, channel_uid: str) -> bool:
        self.restarted.append(channel_uid)
        return True

    def is_running(self, name: str) -> bool:
        return name in self.adapters

    def start_pending(self, channel_uid: str) -> bool:
        return False

    def websocket_state(self, channel_uid: str) -> tuple[str, str | None] | None:
        return self.websockets.get(channel_uid)

    def adapter(self, name: str) -> _StubAdapter | None:
        return self.adapters.get(name)


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
    extra: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
async def ctx(tmp_path) -> AsyncIterator[_Ctx]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"channel": make_channel_kind()}, repo=make_resource_repo(), audit=audit
    )
    peers = ChannelPeerRepo()
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
    )
    set_channel_service(None)
    set_active_token(None)
    await engine.dispose()


def _client(app: FastAPI, *, token: str | None = _TOKEN) -> AsyncClient:
    headers = {"X-Coffer-Token": token} if token is not None else {}
    return AsyncClient(transport=ASGITransport(app), base_url="http://t", headers=headers)


async def _pair(
    ctx: _Ctx, resource_uid: str, *, chat_id: str = "emp-1", display: str = "Yu"
) -> None:
    await ctx.peers.upsert(
        ChannelPeer(
            resource_uid=resource_uid,
            chat_id=chat_id,
            display_name=display,
            paired_at=datetime.now(tz=UTC),
            sender_id=chat_id,
        )
    )
    # The conversation pointer lives on the DM's thread row, not on the peer.
    await ctx.threads.set_active_conversation(resource_uid, chat_id, "", "conv-9")


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
    assert ctx.pairing.pending(ctx.tg_uid) is True  # the service's manager holds the code


@pytest.mark.acceptance(
    spec="channels", scenario="a channel's settings arrive with their defaults filled in"
)
async def test_status_telegram_defaults(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")
    assert r.status_code == 200
    body = r.json()
    # The commands the channel answers ride along, from the one roster: every word
    # with its argument hint and both descriptions (the Overview lists them).
    commands = body.pop("commands")
    assert [c["name"] for c in commands][:3] == ["new", "stop", "model"]
    assert {"name", "args", "description", "description_zh"} == set(commands[0])
    assert "kb" not in {c["name"] for c in commands}
    assert body == {
        # Both travel: the uid is what a surface addresses the channel by, the
        # name is what it shows. A status that carried only the label would
        # leave every client that has to call back needing a second lookup.
        "uid": ctx.tg_uid,
        "name": "tg",
        "channel_type": "telegram",
        "enabled": True,
        "running": False,
        "pending_pairing": False,
        "people": [],
        "inbound": None,  # telegram's inbound is its own polling, reported by `running`
        "diagnostics": [],  # nothing contradicts the configuration
        "secret_approval": None,  # its secret is not waiting on anyone
        "starting": False,
        "title": None,  # none set, so a surface shows the name
        "handoff": None,  # nothing to hand to an agent
        # Where new conversations start while the channel marks no default.
        "workspace_directory": str(content_root() / "workspace"),
        # The typed configuration with every default filled in: the one place a
        # surface reads a default from, instead of carrying its own copy.
        "settings": {
            "channel_type": "telegram",
            "bot_token_ref": "channel/tg/bot",
            "default_agent": None,
            "default_agent_config": None,
            "require_mention": True,
            "ignore_other_mentions": False,
            "wait_after_text_seconds": 1.5,
            "wait_after_forward_seconds": 5.0,
            "show_steps": True,
            "new_conversation_after_idle_hours": 24.0,
            "directories": [],
            "direct_system_prompt": "",
            "group_system_prompt": "",
        },
    }


@pytest.mark.acceptance(
    spec="channels",
    scenario="a channel whose secret waits for approval says so and starts once approved",
)
async def test_status_names_a_secret_waiting_for_approval(ctx: _Ctx) -> None:
    ctx.runtime.withheld[ctx.st_uid] = "pending"
    async with _client(ctx.app) as c:
        r = await c.get(f"/api/v1/channels/{ctx.st_uid}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is False
    assert body["secret_approval"]["state"] == "pending"
    assert body["secret_approval"]["secret_ref"]


@pytest.mark.acceptance(
    spec="channels",
    scenario="channel status reports runtime, pairing, and callback details",
)
async def test_status_reports_runtime_pairing_and_callback_details(ctx: _Ctx) -> None:
    ctx.runtime.adapters[ctx.st_uid] = _StubAdapter()
    ctx.runtime.websockets[ctx.st_uid] = ("connected", None)
    await _pair(ctx, ctx.st_uid)
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
    (person,) = body["people"]
    assert person["chat_id"] == "emp-1"
    assert person["sender_id"] == "emp-1"
    assert person["display_name"] == "Yu"
    assert person["active_conversation_id"] == "conv-9"
    # The channel type's own inbound state: for SeaTalk, its websocket
    # connection, and nothing about a listener, port, path, URL or tunnel.
    assert body["inbound"] == {"websocket_state": "connected", "websocket_error": None}
    assert "callback" not in body


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
    ctx.runtime.adapters[mg.uid] = _StubAdapter()  # adapter live -> healthy
    await _pair(ctx, mg.uid)

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
    assert body["people"][0]["display_name"] == "Yu"  # paired owner
    assert body["people"][0]["chat_id"] == "emp-1"


async def test_several_people_are_listed_and_one_can_be_removed(ctx: _Ctx) -> None:
    """Spec channels "Gate inbound traffic on sender identity": the status lists everyone paired,
    earliest first; removing one leaves the rest, and removing a stranger is a 404."""
    await _pair(ctx, ctx.tg_uid, chat_id="emp-1", display="Yu")
    await _pair(ctx, ctx.tg_uid, chat_id="emp-2", display="Ann")
    async with _client(ctx.app) as c:
        listed = (await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")).json()
        assert [p["display_name"] for p in listed["people"]] == ["Yu", "Ann"]

        gone = await c.delete(f"/api/v1/channels/{ctx.tg_uid}/people/emp-1")
        assert gone.status_code == 204
        after = (await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")).json()
        assert [p["display_name"] for p in after["people"]] == ["Ann"]

        again = await c.delete(f"/api/v1/channels/{ctx.tg_uid}/people/emp-1")
        assert again.status_code == 404
        assert again.json()["error"]["code"] == "CHANNEL_PERSON_NOT_FOUND"

        # The last person may go: a channel with nobody paired is where every one starts.
        assert (await c.delete(f"/api/v1/channels/{ctx.tg_uid}/people/emp-2")).status_code == 204
        empty = (await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")).json()
        assert empty["people"] == []


async def test_a_pairing_code_may_name_the_person_it_replaces(ctx: _Ctx) -> None:
    await _pair(ctx, ctx.tg_uid, chat_id="emp-1")
    async with _client(ctx.app) as c:
        ok = await c.post(f"/api/v1/channels/{ctx.tg_uid}/pairing-code", json={"replaces": "emp-1"})
        assert ok.status_code == 200
        bad = await c.post(f"/api/v1/channels/{ctx.tg_uid}/pairing-code", json={"replaces": "x"})
        assert bad.status_code == 404

        # Cancelling takes the outstanding code away.
        assert (await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")).json()["pending_pairing"]
        assert (await c.delete(f"/api/v1/channels/{ctx.tg_uid}/pairing-code")).status_code == 204
        assert not (await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")).json()["pending_pairing"]


async def test_notify_delivers_to_paired_peer(ctx: _Ctx) -> None:
    adapter = _StubAdapter()
    ctx.runtime.adapters[ctx.tg_uid] = adapter
    await _pair(ctx, ctx.tg_uid, chat_id="555")
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/notify", json={"text": "build green"})
    assert r.status_code == 200
    assert r.json() == {"sent": True}
    assert adapter.sent == [("555", "build green")]


async def test_notify_unpaired_channel_is_409(ctx: _Ctx) -> None:
    ctx.runtime.adapters[ctx.tg_uid] = _StubAdapter()
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/notify", json={"text": "hi"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CHANNEL_NOT_PAIRED"


async def test_notify_with_adapter_down_is_409(ctx: _Ctx) -> None:
    await _pair(ctx, ctx.tg_uid)  # paired, but no adapter running
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/notify", json={"text": "hi"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CHANNEL_NOT_RUNNING"


async def test_notify_rejects_empty_text(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/notify", json={"text": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CONFIG_INVALID"


async def test_the_webhook_routes_are_gone(ctx: _Ctx) -> None:
    """No route here is called by an IM platform any more: SeaTalk pushes down
    the websocket connection the daemon holds."""
    ctx.runtime.adapters[ctx.st_uid] = _StubAdapter()
    async with _client(ctx.app) as c:
        for path in (
            f"/api/v1/channels/{ctx.st_uid}/events",
            f"/api/v1/channels/{ctx.st_uid}/callback-test",
        ):
            r = await c.post(path, json={"event_type": "x", "event": {}})
            assert r.status_code in (404, 405), (path, r.status_code)


async def test_ingest_hands_a_pushed_event_to_the_adapter(ctx: _Ctx) -> None:
    """``ChannelService.ingest_event`` is the seam the websocket controller
    feeds; it returns once the adapter has handled the event."""
    adapter = _StubAdapter()
    ctx.runtime.adapters[ctx.st_uid] = adapter
    envelope = {
        "event_type": "message_from_bot_subscriber",
        "timestamp": 1718000000,
        "event": {"employee_code": "emp-1", "message": {"tag": "text", "text": {"content": "hi"}}},
    }
    await get_channel_service().ingest_event(ctx.st_uid, envelope)
    for _ in range(100):
        if adapter.events:
            break
        await asyncio.sleep(0.01)
    assert adapter.events == [envelope]  # the raw envelope reached handle_event


async def test_ingest_with_the_adapter_down_is_refused(ctx: _Ctx) -> None:
    with pytest.raises(ChannelNotRunning):
        await get_channel_service().ingest_event(ctx.st_uid, {"event_type": "x", "event": {}})


async def test_channel_status_carries_the_resource_title(ctx: _Ctx) -> None:
    """spec resource-framework "Carry an optional editable title on the kinds that have one":
    the status read carries the channel's title beside its unchanged name."""
    async with _client(ctx.app) as c:
        r = await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")
        assert r.json()["title"] is None
        await ctx.resources.set_title(ctx.tg_uid, "Team bot", actor="test")
        r = await c.get(f"/api/v1/channels/{ctx.tg_uid}/status")
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["title"]) == ("tg", "Team bot")


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="a missing sdk is handed to an agent from the channel page",
)
async def test_status_hands_a_missing_sdk_to_an_agent(
    ctx: _Ctx, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    vendor = tmp_path / "sdk-home"
    monkeypatch.setenv("COFFER_SEATALK_SDK_DIR", str(vendor))
    ctx.runtime.adapters[ctx.st_uid] = _StubAdapter()
    ctx.runtime.websockets[ctx.st_uid] = ("sdk_missing", "not found")
    async with _client(ctx.app) as c:
        missing = (await c.get(f"/api/v1/channels/{ctx.st_uid}/status")).json()
        ctx.runtime.websockets[ctx.st_uid] = ("connected", None)
        connected = (await c.get(f"/api/v1/channels/{ctx.st_uid}/status")).json()
    prompt = missing["handoff"]["prompt"]
    # Where the daemon loads it from, where the person downloads it, and how
    # the agent confirms it — the download itself stays with the person.
    assert f"{vendor}/seatalk_oapi_sdk/" in prompt
    assert "$COFFER_SEATALK_SDK_DIR" in prompt
    assert "https://open.seatalk.io/docs/WebSocket-Event-Callback" in prompt
    assert "~/Downloads" in prompt
    assert "coffer channel" not in prompt
    assert "websocket (connected)" in prompt
    assert "I will log in myself" in prompt
    assert connected["handoff"] is None


@pytest.mark.acceptance(spec="channels", scenario="a restart rebuilds the adapter on demand")
async def test_restart_route_restarts_the_adapter_and_reports_whether_it_runs(ctx: _Ctx) -> None:
    async with _client(ctx.app) as c:
        r = await c.post(f"/api/v1/channels/{ctx.tg_uid}/restart")
        missing = await c.post("/api/v1/channels/no-such-uid/restart")
    assert r.status_code == 200
    assert r.json() == {"running": True}
    assert ctx.runtime.restarted == [ctx.tg_uid]
    assert missing.status_code == 404


@pytest.mark.acceptance(
    spec="channels", scenario="a paired person's picture is served from the running adapter"
)
async def test_person_avatar_route_serves_the_picture_then_forgets_it_on_removal(
    ctx: _Ctx, tmp_path
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8

    class _PictureAdapter(_StubAdapter):
        async def fetch_avatar(self, sender_id: str) -> bytes | None:
            return png if sender_id == "emp-1" else None

    ctx.runtime.adapters[ctx.tg_uid] = _PictureAdapter()
    store = FileAvatarStore(tmp_path / "avatars")
    set_channel_avatars(PersonAvatars(store=store, peers=ctx.peers, adapter_of=ctx.runtime.adapter))
    try:
        await _pair(ctx, ctx.tg_uid, chat_id="emp-1")
        await _pair(ctx, ctx.tg_uid, chat_id="emp-2", display="Bo")
        async with _client(ctx.app) as c:
            r = await c.get(f"/api/v1/channels/{ctx.tg_uid}/people/emp-1/avatar")
            assert r.status_code == 200
            assert r.headers["content-type"] == "image/png"
            assert r.content == png
            # No picture on the platform, or nobody by that id: initials.
            assert (
                await c.get(f"/api/v1/channels/{ctx.tg_uid}/people/emp-2/avatar")
            ).status_code == 204
            assert (
                await c.get(f"/api/v1/channels/{ctx.tg_uid}/people/zz/avatar")
            ).status_code == 204
            assert (
                await c.delete(f"/api/v1/channels/{ctx.tg_uid}/people/emp-1")
            ).status_code == 204
        assert store.read(ctx.tg_uid, "emp-1") is None
    finally:
        set_channel_avatars(None)
