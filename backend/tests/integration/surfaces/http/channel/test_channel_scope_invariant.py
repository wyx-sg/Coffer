"""One invariant, both write paths (spec channels FR-079).

A channel's ``default_agent`` must be an agent the channel may drive. Two
endpoints can break that — ``PATCH /resources/channel/{name}`` edits the config
and ``PUT /resources/channel/{name}/scope`` edits the reach — so both enforce
it, and the inconsistent state cannot be stored at all. Driven over the real
resource routes because the point is that the ANSWER is a 4xx the user sees,
not a log line after a silent success.

An empty agent axis is the one thing both paths always accept: it is the
vault-wide meaning of dormant (the channel is off), and off must not also mean
frozen. The machine axis is not judged on either path at all — narrowing a
channel to another machine is how a converged vault hands the surface over.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.audit_service import AuditService
from coffer.application.channel.kind import make_channel_kind
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import Scope
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router

_TOKEN = "test-token"
_SCOPE_URL = "/api/v1/resources/channel/tg/scope"
_CONFIG_URL = "/api/v1/resources/channel/tg"


@pytest.fixture
async def client(tmp_path) -> AsyncIterator[tuple[AsyncClient, ResourceService]]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    # Both injections the composition root makes, so the config path's
    # default_agent check is live too — the scope path's check needs none.
    kind = make_channel_kind(
        agent_keys=lambda: ["claude_code", "codex"],
        scope_of=lambda ref: _scope_of(svc, ref),
    )
    svc = ResourceService(kinds={"channel": kind}, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    await svc.register(
        "channel",
        "tg",
        {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot"},
        actor="test",
    )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: svc
    set_active_token(_TOKEN)
    transport = ASGITransport(app)
    async with AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        yield c, svc
    set_active_token(None)
    await engine.dispose()


async def _scope_of(svc: ResourceService, ref: ResourceRef) -> Scope | None:
    return (await svc.get(ref)).scope


@pytest.mark.acceptance(
    spec="channels",
    scenario="reject narrowing a channel's scope past its default agent",
)
async def test_narrowing_past_the_default_agent_is_rejected_not_silently_accepted(client) -> None:
    c, svc = client
    # The channel's default_agent is claude_code (the config default), so this
    # narrowing would leave it able to drive nothing.
    r = await c.put(_SCOPE_URL, json={"scope": {"agents": ["codex"]}})

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "SCOPE_INVALID"
    # Names both sides, so the owner can see the two ways out.
    message = r.json()["error"]["message"]
    assert "claude_code" in message
    assert "codex" in message
    # Rejected BEFORE persistence: the reach the user narrowed away is intact.
    assert (await svc.get(ResourceRef("channel", "tg"))).scope is None


async def test_a_scope_that_keeps_the_default_agent_is_accepted(client) -> None:
    c, _svc = client
    r = await c.put(_SCOPE_URL, json={"scope": {"agents": ["claude_code"]}})

    assert r.status_code == 200, r.text
    assert r.json()["scope"] == {"agents": ["claude_code"], "machines": None}


async def test_the_dormant_scope_is_accepted(client) -> None:
    """``[]`` is the deliberate "off" switch, never a rejected narrowing."""
    c, _svc = client
    r = await c.put(_SCOPE_URL, json={"scope": {"agents": []}})

    assert r.status_code == 200, r.text
    assert r.json()["scope"] == {"agents": [], "machines": None}


@pytest.mark.acceptance(
    spec="channels",
    scenario="edit a dormant channel's configuration",
)
async def test_a_dormant_channels_config_stays_editable(client) -> None:
    """The owner switched the channel off, then found its bot token was wrong.
    Off must not mean frozen."""
    c, svc = client
    assert (await c.put(_SCOPE_URL, json={"scope": {"agents": []}})).status_code == 200

    r = await c.patch(
        _CONFIG_URL,
        json={"config": {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-v2"}},
    )

    assert r.status_code == 200, r.text
    assert r.json()["config"]["bot_token_ref"] == "channel/tg/bot-v2"
    # Still dormant — an edit is not a way to accidentally switch it back on.
    assert (await svc.get(ResourceRef("channel", "tg"))).scope == Scope(agents=[], machines=None)


async def test_widening_the_scope_back_works(client) -> None:
    c, _svc = client
    assert (await c.put(_SCOPE_URL, json={"scope": {"agents": []}})).status_code == 200

    r = await c.put(_SCOPE_URL, json={"scope": None})

    assert r.status_code == 200, r.text
    assert r.json()["scope"] is None


async def test_the_config_path_still_rejects_a_default_agent_outside_the_scope(client) -> None:
    """The other half of the invariant, unchanged: with a non-empty scope in
    place, an edit cannot re-bind the channel to an agent outside it."""
    c, _svc = client
    assert (await c.put(_SCOPE_URL, json={"scope": {"agents": ["claude_code"]}})).status_code == 200

    r = await c.patch(
        _CONFIG_URL,
        json={
            "config": {
                "channel_type": "telegram",
                "bot_token_ref": "channel/tg/bot",
                "default_agent": "codex",
            }
        },
    )

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "CONFIG_INVALID"
    assert "outside this channel's scope" in r.json()["error"]["message"]


async def test_a_machine_only_narrowing_is_not_judged_by_either_path(client) -> None:
    """Neither write path reads the machine axis.

    Handing a channel to another machine is a legitimate edit — it is how a
    converged vault decides who answers the bot — and it says nothing about the
    agents the channel may drive, so the ``default_agent`` invariant has nothing
    to object to. Its config must stay editable afterwards too: a channel
    nobody can correct from where they are sitting is the failure this avoids.
    """
    c, svc = client
    r = await c.put(_SCOPE_URL, json={"scope": {"machines": ["some-other-machine"]}})

    assert r.status_code == 200, r.text
    assert (await svc.get(ResourceRef("channel", "tg"))).scope == Scope(
        agents=None, machines=["some-other-machine"]
    )

    edit = await c.patch(
        _CONFIG_URL,
        json={"config": {"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-v2"}},
    )
    assert edit.status_code == 200, edit.text
