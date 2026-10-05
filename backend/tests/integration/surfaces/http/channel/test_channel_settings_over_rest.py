"""A channel's settings, lifecycle and reach over REST (spec channels).

The Channels page writes through ``/api/v1/resources``; these tests stand where
the page stands, over a real ResourceService on SQLite with the channel kind.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.service import ChannelService
from coffer.application.resource_service import ResourceService
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
from coffer.surfaces.http.channel_routes import router as channel_router
from coffer.surfaces.http.channel_routes import set_channel_service
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router
from tests.support.vault_stores import make_resource_repo

_TOKEN = "test-token"
_TG = {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot"}
_ST = {"channel_type": "seatalk", "app_id": "app-1", "app_secret_ref": "channel/st/secret"}


class _Runtime:
    def __init__(self) -> None:
        self.websockets: dict[str, tuple[str, str | None]] = {}

    def secret_withheld(self, channel_uid: str) -> str | None:
        return None

    async def restart(self, channel_uid: str) -> bool:
        return True

    def is_running(self, name: str) -> bool:
        return True

    def start_pending(self, channel_uid: str) -> bool:
        return False

    def websocket_state(self, channel_uid: str) -> tuple[str, str | None] | None:
        return self.websockets.get(channel_uid)

    def adapter(self, name: str) -> None:
        return None

    async def local_machine_id(self) -> str | None:
        return None


@dataclass
class _Ctx:
    http: AsyncClient
    resources: ResourceService
    audit: AuditService
    runtime: _Runtime


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
    runtime = _Runtime()
    service = ChannelService(
        resources=resources,
        peers=ChannelPeerRepo(),
        threads=ChannelThreadConversationRepo(sm),
        pairing=PairingManager(),
        runtime=runtime,
        audit=audit,
    )
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.include_router(channel_router)
    app.dependency_overrides[get_resource_service] = lambda: resources
    app.dependency_overrides[get_audit_service] = lambda: audit
    set_channel_service(service)
    set_active_token(_TOKEN)
    http = AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    )
    yield _Ctx(http=http, resources=resources, audit=audit, runtime=runtime)
    await http.aclose()
    set_channel_service(None)
    set_active_token(None)
    await engine.dispose()


async def _register(ctx: _Ctx, name: str = "tg", config: dict[str, Any] | None = None) -> dict:
    r = await ctx.http.post(
        "/api/v1/resources", json={"kind": "channel", "name": name, "config": config or _TG}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _patch(ctx: _Ctx, uid: str, **config: Any) -> Any:
    """Patch the channel the way the settings tab does: the stored config plus the change."""
    stored = (await ctx.http.get(f"/api/v1/resources/{uid}")).json()["config"]
    return await ctx.http.patch(f"/api/v1/resources/{uid}", json={"config": {**stored, **config}})


async def _config(ctx: _Ctx, uid: str) -> dict[str, Any]:
    return (await ctx.http.get(f"/api/v1/resources/{uid}")).json()["config"]


@pytest.mark.acceptance(
    spec="channels", scenario="register a channel from the Add dialog and list it"
)
async def test_a_registered_channel_appears_in_the_list(ctx: _Ctx) -> None:
    made = await _register(ctx, "tg")
    await _register(ctx, "st", _ST)
    listed = await ctx.http.get("/api/v1/resources", params={"kind": "channel"})
    assert listed.status_code == 200
    names = {item["name"] for item in listed.json()["resources"]}
    assert names == {"tg", "st"}
    assert made["kind"] == "channel"


@pytest.mark.acceptance(
    spec="channels", scenario="the group-gating switches are edited in the Settings tab"
)
async def test_gating_switches_change_and_nothing_else_does(ctx: _Ctx) -> None:
    uid = (await _register(ctx))["uid"]
    before = await _config(ctx, uid)
    assert before.get("require_mention", True) is True
    assert before.get("ignore_other_mentions", False) is False

    r = await _patch(ctx, uid, require_mention=False, ignore_other_mentions=True)
    assert r.status_code == 200, r.text
    after = await _config(ctx, uid)
    assert after["require_mention"] is False and after["ignore_other_mentions"] is True
    assert after["bot_token_ref"] == _TG["bot_token_ref"]
    assert {
        k: v for k, v in after.items() if k not in ("require_mention", "ignore_other_mentions")
    } == {k: v for k, v in before.items() if k not in ("require_mention", "ignore_other_mentions")}


@pytest.mark.acceptance(
    spec="channels", scenario="a channel's lifecycle and reach run through the resource routes"
)
async def test_title_scope_disable_and_delete_are_resource_operations(ctx: _Ctx) -> None:
    uid = (await _register(ctx))["uid"]
    before = await _config(ctx, uid)

    titled = await ctx.http.patch(f"/api/v1/resources/{uid}", json={"title": "Phone bot"})
    assert titled.status_code == 200, titled.text
    assert titled.json()["title"] == "Phone bot"
    assert await _config(ctx, uid) == before

    scoped = await ctx.http.put(
        f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": ["codex-uid"]}}
    )
    assert scoped.status_code == 200, scoped.text
    got = (await ctx.http.get(f"/api/v1/resources/{uid}/scope")).json()
    assert got["scope"]["agents"] == ["codex-uid"]

    off = await ctx.http.post(f"/api/v1/resources/{uid}/disable")
    assert off.status_code == 200 and off.json()["enabled"] is False

    gone = await ctx.http.delete(f"/api/v1/resources/{uid}")
    assert gone.status_code == 204
    listed = await ctx.http.get("/api/v1/resources", params={"kind": "channel"})
    assert listed.json()["resources"] == []

    events = [e.event_type for e in await ctx.audit.query(kind="channel", limit=50)]
    for expected in (
        "resource_created",
        "resource_updated",
        "resource_scope_updated",
        "resource_disabled",
        "resource_deleted",
    ):
        assert expected in events, (expected, events)


@pytest.mark.acceptance(
    spec="channels", scenario="the quiet windows are edited in the channel's settings"
)
async def test_the_quiet_windows_are_edited_and_bounded(ctx: _Ctx) -> None:
    uid = (await _register(ctx))["uid"]
    r = await _patch(ctx, uid, wait_after_text_seconds=0, wait_after_forward_seconds=8)
    assert r.status_code == 200, r.text
    config = await _config(ctx, uid)
    assert config["wait_after_text_seconds"] == 0
    assert config["wait_after_forward_seconds"] == 8
    assert config.get("require_mention", True) is True
    refused = await _patch(ctx, uid, wait_after_text_seconds=61)
    assert refused.status_code == 422, refused.text
    assert (await _config(ctx, uid))["wait_after_text_seconds"] == 0


@pytest.mark.acceptance(
    spec="channels", scenario="the step lines are hidden in the channel's settings"
)
async def test_step_lines_are_switched_off_then_on(ctx: _Ctx) -> None:
    uid = (await _register(ctx))["uid"]
    assert (await _config(ctx, uid)).get("show_steps", True) is True
    assert (await _patch(ctx, uid, show_steps=False)).status_code == 200
    assert (await _config(ctx, uid))["show_steps"] is False
    assert (await _patch(ctx, uid, show_steps=True)).status_code == 200
    assert (await _config(ctx, uid))["show_steps"] is True


@pytest.mark.acceptance(
    spec="channels", scenario="the ping threshold is edited in the channel's settings"
)
async def test_the_ping_threshold_is_edited_and_bounded(ctx: _Ctx) -> None:
    uid = (await _register(ctx))["uid"]
    assert (await _patch(ctx, uid, notify_after_seconds=0)).status_code == 200
    assert (await _config(ctx, uid))["notify_after_seconds"] == 0
    refused = await _patch(ctx, uid, notify_after_seconds=3601)
    assert refused.status_code == 422, refused.text


@pytest.mark.acceptance(
    spec="channels/seatalk", scenario="status names the websocket connection state"
)
async def test_status_reports_only_the_websocket_state(ctx: _Ctx) -> None:
    up = (await _register(ctx, "up", _ST))["uid"]
    down = (await _register(ctx, "down", _ST))["uid"]
    ctx.runtime.websockets[up] = ("connected", None)
    ctx.runtime.websockets[down] = ("error", "register handshake refused: bad app secret")

    up_body = (await ctx.http.get(f"/api/v1/channels/{up}/status")).json()
    down_body = (await ctx.http.get(f"/api/v1/channels/{down}/status")).json()
    assert up_body["inbound"] == {"websocket_state": "connected", "websocket_error": None}
    assert down_body["inbound"] == {
        "websocket_state": "error",
        "websocket_error": "register handshake refused: bad app secret",
    }
    for body in (up_body, down_body):
        assert set(body["inbound"]) == {"websocket_state", "websocket_error"}
        assert "callback" not in body
        rendered = str(body)
        for word in ("listener", "127.0.0.1", "/seatalk/", "tunnel", "https://"):
            assert word not in rendered


async def test_status_names_the_workspace_new_conversations_fall_back_to(ctx: _Ctx) -> None:
    uid = (await _register(ctx, "tg", _TG))["uid"]

    body = (await ctx.http.get(f"/api/v1/channels/{uid}/status")).json()

    assert body["workspace_directory"] == str(content_root() / "workspace")
