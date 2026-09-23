"""One invariant, both write paths.

See spec channels "Limit the agents a channel may drive to its scope".

A channel's ``default_agent`` must be an agent the channel may drive. Two
endpoints can break that — ``PATCH /resources/{uid}`` edits the config and
``PUT /resources/{uid}/scope`` edits the reach — so both enforce it, and the
inconsistent state cannot be stored at all. Driven over the real resource
routes because the point is that the ANSWER is a 4xx the user sees, not a log
line after a silent success.

An empty agent list is the one thing both paths always accept: it is the
vault-wide meaning of dormant (the channel is off), and off must not also mean
frozen.

Both sides of the comparison are agent UIDS
(ADR resource-identity-is-an-immutable-uid): a scope names agents by uid and so
does ``default_agent``, so the kind compares them directly and needs nothing
injected to do it. That is what this file used to be about in reverse — a scope
written in agent RESOURCE names against a ``default_agent`` written as an agent
KEY, with a map injected to reconcile the two. The map is gone; the only thing
still injected is a uid→label reader, and it decides nothing, it just writes the
refusals in words an owner can act on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.channel.kind import make_channel_kind
from coffer.application.resource_service import ResourceService
from coffer.domain.scope import Scope
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router

_TOKEN = "test-token"

#: Two registered agents, named the way a user names them. Neither name is the
#: agent key it maps to, and neither is the uid the vault mints for it — which
#: is the point: nothing below may pass by comparing a label to anything.
_AGENTS = {"claude-code": "claude_code", "codex-cli": "codex"}


@dataclass
class _Env:
    """What every test here addresses the vault by: uids, plus the client."""

    client: AsyncClient
    svc: ResourceService
    channel_uid: str
    #: agent name -> the uid a scope is actually written in.
    agent_uids: dict[str, str]

    @property
    def scope_url(self) -> str:
        return f"/api/v1/resources/{self.channel_uid}/scope"

    @property
    def config_url(self) -> str:
        return f"/api/v1/resources/{self.channel_uid}"

    def uid_of(self, agent_name: str) -> str:
        return self.agent_uids[agent_name]


@pytest.fixture
async def env(tmp_path) -> AsyncIterator[_Env]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    async def _agent_names() -> Mapping[str, str]:
        return {a.uid: a.name for a in await svc.list(kind="agent")}

    # The one injection the composition root still makes, so both paths' checks
    # are live — not to compare through, but so a refusal names the agents in
    # labels instead of bare uids.
    kind = make_channel_kind(agent_names=_agent_names)
    svc = ResourceService(
        kinds={"channel": kind, "agent": make_agent_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    agent_uids: dict[str, str] = {}
    for agent_name, agent_type in _AGENTS.items():
        registered = await svc.register(
            "agent",
            agent_name,
            {"type": agent_type, "config_dir": str(tmp_path / agent_name)},
            actor="test",
            allow_lifecycle_kind=True,
        )
        agent_uids[agent_name] = registered.uid
    # ``default_agent`` is written explicitly because there is no default left
    # to write it: a uid is minted per vault, so no schema constant can stand
    # for "the usual agent" and a channel bound to nobody drives nothing.
    channel = await svc.register(
        "channel",
        "tg",
        {
            "channel_type": "telegram",
            "bot_token_ref": "channel/tg/bot",
            "default_agent": agent_uids["claude-code"],
        },
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
        yield _Env(client=c, svc=svc, channel_uid=channel.uid, agent_uids=agent_uids)
    set_active_token(None)
    await engine.dispose()


@pytest.mark.acceptance(
    spec="channels",
    scenario="reject narrowing a channel's scope past its default agent",
)
async def test_narrowing_past_the_default_agent_is_rejected_not_silently_accepted(
    env: _Env,
) -> None:
    # The channel's default_agent is claude-code, so this narrowing would leave
    # it able to drive nothing.
    r = await env.client.put(env.scope_url, json={"scope": {"agents": [env.uid_of("codex-cli")]}})

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "SCOPE_INVALID"
    # Names both sides, so the owner can see the two ways out. In LABELS: the
    # stored values are uids now, and a refusal spelled in uids names nothing
    # the owner recognises.
    message = r.json()["error"]["message"]
    assert "claude-code" in message
    assert "codex-cli" in message
    # Rejected BEFORE persistence: the reach the user narrowed away is intact.
    assert (await env.svc.get(env.channel_uid)).scope is None


async def test_a_scope_that_keeps_the_default_agent_is_accepted(env: _Env) -> None:
    """Narrowed to the agent the channel is bound to — the narrowing a user can
    actually express, and the one the two vocabularies used to refuse."""
    r = await env.client.put(env.scope_url, json={"scope": {"agents": [env.uid_of("claude-code")]}})

    assert r.status_code == 200, r.text
    assert r.json()["scope"] == {"agents": [env.uid_of("claude-code")]}


async def test_a_scope_naming_the_agent_by_label_instead_is_refused(env: _Env) -> None:
    """And the mirror: a name is not an identity, so it narrows the channel to a
    resource this vault does not hold — which drives nothing. It reads as a
    narrowing past the default agent, because that is what it is.

    This was the "agent key is not a resource name" case while an agent answered
    to two names. One vocabulary later it is the case that matters more: no
    label fallback anywhere, so a scope written in names is refused rather than
    quietly resolved into the uids it looks like it means.
    """
    r = await env.client.put(env.scope_url, json={"scope": {"agents": ["claude-code"]}})

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "SCOPE_INVALID"


async def test_the_dormant_scope_is_accepted(env: _Env) -> None:
    """``[]`` is the deliberate "off" switch, never a rejected narrowing."""
    r = await env.client.put(env.scope_url, json={"scope": {"agents": []}})

    assert r.status_code == 200, r.text
    assert r.json()["scope"] == {"agents": []}


@pytest.mark.acceptance(
    spec="channels",
    scenario="edit a dormant channel's configuration",
)
async def test_a_dormant_channels_config_stays_editable(env: _Env) -> None:
    """The owner switched the channel off, then found its bot token was wrong.
    Off must not mean frozen."""
    assert (await env.client.put(env.scope_url, json={"scope": {"agents": []}})).status_code == 200

    r = await env.client.patch(
        env.config_url,
        json={
            "config": {
                "channel_type": "telegram",
                "bot_token_ref": "channel/tg/bot-v2",
                "default_agent": env.uid_of("claude-code"),
            }
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["config"]["bot_token_ref"] == "channel/tg/bot-v2"
    # Still dormant — an edit is not a way to accidentally switch it back on.
    assert (await env.svc.get(env.channel_uid)).scope == Scope(agents=[])


async def test_widening_the_scope_back_works(env: _Env) -> None:
    assert (await env.client.put(env.scope_url, json={"scope": {"agents": []}})).status_code == 200

    r = await env.client.put(env.scope_url, json={"scope": None})

    assert r.status_code == 200, r.text
    assert r.json()["scope"] is None


async def test_the_config_path_still_rejects_a_default_agent_outside_the_scope(env: _Env) -> None:
    """The other half of the invariant, unchanged: with a non-empty scope in
    place, an edit cannot re-bind the channel to an agent outside it."""
    assert (
        await env.client.put(env.scope_url, json={"scope": {"agents": [env.uid_of("claude-code")]}})
    ).status_code == 200

    r = await env.client.patch(
        env.config_url,
        json={
            "config": {
                "channel_type": "telegram",
                "bot_token_ref": "channel/tg/bot",
                "default_agent": env.uid_of("codex-cli"),
            }
        },
    )

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "CONFIG_INVALID"
    assert "outside this channel's scope" in r.json()["error"]["message"]
