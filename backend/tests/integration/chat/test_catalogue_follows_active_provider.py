"""The model catalogue follows the connection the agent runs on.

Real ``ProviderService`` over a real SQLite file, the real composition-root
adapter (``_ActiveProviderModels``), and the real on-disk discovery source, so
the whole chain the bug ran through is exercised: register an openai-compatible
gateway, route it at Claude Code, activate it — and the catalogue must stop
offering models only the CLI's own login can serve.

The regression it guards: the channel ``/model`` card offered ``claude-opus-5``
while every turn went to a gateway that has never heard of it, so tapping it
failed the turn at the SDK.

The agents are REGISTERED rows here rather than a hand-built list, which they
did not have to be before: a connection's reach is a scope holding agent UIDS
(ADR identity-is-the-uid-inside-the-file), so resolving that reach back into
the agent TYPE this catalogue is asked about only works against a registry that
actually holds the agents.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.audit_service import AuditService
from coffer.application.channel.selection_cards import model_card
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.service import ProviderService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import CuratedModel, Protocol
from coffer.domain.provider.modality import Modality
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.agent.model_discovery import NativeConfigModelDiscovery
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.agent_provider_routes import router as agent_provider_router
from coffer.surfaces.http.chat.dependencies import get_agent_registry, get_model_catalog
from coffer.surfaces.http.chat_wiring import _ActiveProviderModels
from coffer.surfaces.http.provider_dependencies import set_provider_service
from tests.support.facets import agent_catalog
from tests.support.vault_stores import make_resource_repo
from tests.unit.chat.conftest import FakeAgentProvider

_NOW = dt.datetime(2026, 9, 11, tzinfo=dt.UTC)

#: What the CLI's own login can run, as Claude Code caches it on disk.
_CLI_MODELS = ["claude-opus-5", "claude-sonnet-5"]

#: What the user ticked on the gateway's detail page. Both are CHAT models —
#: the second's name notwithstanding, because a curated entry's modality is
#: STORED, never read back out of its id.
_GATEWAY_MODELS = ["agnes-2.5-pro-beta", "agnes-video-2.5"]

#: The agents this vault holds, as a user names them — deliberately not the
#: agent keys they map to, so nothing here can pass by comparing the two.
_AGENTS = {t: t.default_name() for t in (AgentType.CLAUDE_CODE, AgentType.CODEX)}


def _text(*ids: str) -> list[CuratedModel]:
    """Curated chat entries — the kind a set holds unless a test says otherwise."""
    return [CuratedModel(id=i) for i in ids]


class _DictStore:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self._d.get(ref)

    def set(self, ref: str, value: str) -> None:
        self._d[ref] = value

    def delete(self, ref: str) -> None:
        self._d.pop(ref, None)


class _RegisteredAgents:
    """The agent registry, narrowed to what both services ask of it.

    Backed by the real resource table rather than a fixed list: the uids a
    connection's scope names are minted at registration, so the only registry
    that can answer for them is the one that minted them.
    """

    def __init__(self, resources: ResourceService) -> None:
        self._resources = resources

    async def list(self) -> list[Resource]:
        return await self._resources.list(kind="agent")

    async def set_connection(
        self, uid: str, connection_uid: str | None, *, actor: str = "api"
    ) -> Resource:
        """What the agent kind does for a switch: write the field on the record."""
        row = await self._resources.get(uid)
        return await self._resources.update_config(
            uid,
            {**row.config, "connection_uid": connection_uid},
            actor,
            allow_lifecycle_kind=True,
        )


class _Env:
    def __init__(
        self,
        providers: ProviderService,
        catalogue: AgentModelCatalogueService,
        resources: ResourceService,
        agent_uids: dict[AgentType, str],
    ) -> None:
        self.providers = providers
        self.catalogue = catalogue
        self.resources = resources
        #: Each agent type's registered uid — what a scope is written in.
        self.agent_uids = agent_uids


@pytest.fixture()
async def env(tmp_path: pathlib.Path) -> AsyncIterator[_Env]:
    config_dir = tmp_path / "claude"
    config_dir.mkdir()
    # Claude Code's own cache of what its login may run — the source the
    # catalogue reads when no provider has taken over.
    (config_dir / ".claude.json").write_text(
        json.dumps(
            {"additionalModelOptionsCache": [{"value": m, "label": m} for m in _CLI_MODELS]}
        ),
        encoding="utf-8",
    )

    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    store = _DictStore()
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"provider": make_provider_kind(), "agent": make_agent_kind()},
        repo=make_resource_repo(),
        audit=audit,
        secrets=store,
    )
    # One agent per type, registered through the service (the agent kind
    # refuses the generic create path) so each has a real uid to be scoped by.
    # Only Claude Code's config dir is the one seeded above: Codex's catalogue
    # is never the thing under test, only what an active connection does to it.
    agent_uids: dict[AgentType, str] = {}
    for agent_type, agent_name in _AGENTS.items():
        dir_of = config_dir if agent_type is AgentType.CLAUDE_CODE else tmp_path / agent_name
        dir_of.mkdir(exist_ok=True)
        registered = await resources.register(
            kind="agent",
            name=agent_name,
            config={"type": agent_type.value, "config_dir": str(dir_of)},
            actor="test",
            allow_lifecycle_kind=True,
        )
        agent_uids[agent_type] = registered.uid
    providers = ProviderService(
        agent_catalog=agent_catalog(),
        resources=resources,
        secrets=store,
        config_store=ConfigFileStore(),
        # The switch writes the agent's record (and its tmp config dir); the
        # catalogue then resolves the connection each AGENT runs on through the
        # real resource table (``_ActiveProviderModels`` below), which is the
        # seam under test.
        agents=_RegisteredAgents(resources),
        audit=audit,
    )
    set_provider_service(providers)
    yield _Env(
        providers,
        AgentModelCatalogueService(
            agents=_RegisteredAgents(resources),
            discovery=NativeConfigModelDiscovery(),
            # A connection's reach names agent uids, so turning it back into an
            # agent type is a registry read — a plain dependency of the adapter.
            provider_models=_ActiveProviderModels(resources=resources),
        ),
        resources,
        agent_uids,
    )
    set_provider_service(None)
    await engine.dispose()


async def _gateway(
    env: _Env, *, models: list[CuratedModel], agents: list[AgentType], name: str = "agnes"
) -> None:
    connection = await env.providers.create(
        name,
        protocol=Protocol.OPENAI,
        base_url="https://agnes.example.test/v1",
        secret_value="sk-test",
        models=models,
    )
    # Which agents a connection reaches is its framework scope now, not a
    # create argument (ADR per-agent-resource-scope) — and the scope names them
    # by uid, not by agent type (ADR identity-is-the-uid-inside-the-file), so
    # the types a test reads at are resolved through the registered rows.
    await env.resources.update_scope(
        connection.uid,
        Scope(agents=[env.agent_uids[a] for a in agents]),
        actor="test",
    )
    for agent in agents:
        await env.providers.activate(connection.uid, agent)


async def test_without_a_provider_the_agent_s_own_models_are_offered(env: _Env) -> None:
    assert await env.catalogue.suggest("claude_code") == _CLI_MODELS


async def test_an_activated_gateway_s_curated_models_replace_the_agent_s(env: _Env) -> None:
    """Every turn now goes to the gateway, so its ids are the only ones that can
    succeed — and the CLI's own names must be gone from the card."""
    await _gateway(env, models=_text(*_GATEWAY_MODELS), agents=[AgentType.CLAUDE_CODE])

    assert await env.catalogue.suggest("claude_code") == _GATEWAY_MODELS


async def test_an_activated_gateway_that_restricts_nothing_leaves_discovery_alone(
    env: _Env,
) -> None:
    """An empty curated set means "no restriction": Coffer knows where the turns
    go but not what that endpoint serves, and it will not ask on a card render.
    The agent's own answer stays the best available, and the provider's detail
    page is where the user makes it accurate."""
    await _gateway(env, models=[], agents=[AgentType.CLAUDE_CODE])

    assert await env.catalogue.suggest("claude_code") == _CLI_MODELS


async def test_a_gateway_activated_for_another_agent_does_not_leak(env: _Env) -> None:
    """Activation is per agent type. A connection routed at Codex says nothing
    about what Claude Code — still on its own login — can run."""
    await _gateway(env, models=_text("gpt-6-codex"), agents=[AgentType.CODEX])

    assert await env.catalogue.suggest("claude_code") == _CLI_MODELS
    assert await env.catalogue.suggest("codex") == ["gpt-6-codex"]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a non-text curated model never reaches a chat model picker",
)
async def test_only_the_text_models_of_a_mixed_connection_are_offered(env: _Env) -> None:
    """One endpoint, one key, three kinds of model. A chat picker may offer only
    the chat one: an embedding or image id handed to a turn could only be
    rejected by the very endpoint that was asked for it, so the narrowing has to
    happen before the card is rendered — not after the turn fails."""
    await _gateway(
        env,
        models=[
            CuratedModel(id="agnes-2.5-pro-beta"),
            CuratedModel(id="agnes-embed-1", modality=Modality.EMBEDDING),
            CuratedModel(id="agnes-canvas-1", modality=Modality.IMAGE),
        ],
        agents=[AgentType.CLAUDE_CODE],
    )

    # The web model picker …
    assert [m.id for m in await env.catalogue.offered("claude_code")] == ["agnes-2.5-pro-beta"]
    # … and the channel ``/model`` card, which starts from the same answer.
    assert await env.catalogue.suggest("claude_code") == ["agnes-2.5-pro-beta"]
    # The agent's own catalogue is untouched by curation — it describes the
    # login, and narrowing is the picker's business (``offered``), not its.
    assert [m.id for m in await env.catalogue.catalogue("claude_code")] == _CLI_MODELS


async def test_a_connection_curating_no_text_model_offers_no_chat_model(env: _Env) -> None:
    """spec provider-switching "Offer only text models to chat pickers": a
    connection that curates something but nothing ``text`` offers no chat model
    rather than falling back to the agent's own catalogue — those are ids the
    endpoint the turns now go to would reject. Asked over the real route every
    web picker reads."""
    await _gateway(
        env,
        models=[CuratedModel(id="agnes-embed-1", modality=Modality.EMBEDDING)],
        agents=[AgentType.CLAUDE_CODE],
    )

    registry = AgentProviderRegistry()
    registry.register(FakeAgentProvider(None, agent_key="claude_code"), display_name="Claude Code")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_provider_router)
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_model_catalog] = lambda: env.catalogue
    token = "test-token-no-text-model"
    set_active_token(token)
    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/agent-providers/claude_code/models", headers={"X-Coffer-Token": token}
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["models"] == []
    # The channel ``/model`` card's model card reads the same answer.
    assert await env.catalogue.suggest("claude_code") == []
    # The login's own catalogue is still the full truth, just not offered.
    assert [m.id for m in await env.catalogue.catalogue("claude_code")] == _CLI_MODELS


def _models_route(env: _Env) -> list[dict[str, object]]:
    """What every picker reads: ``GET /agent-providers/claude_code/models``."""
    registry = AgentProviderRegistry()
    registry.register(FakeAgentProvider(None, agent_key="claude_code"), display_name="Claude Code")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(agent_provider_router)
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_model_catalog] = lambda: env.catalogue
    token = "test-token-fixed-list"
    set_active_token(token)
    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/agent-providers/claude_code/models", headers={"X-Coffer-Token": token}
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["models"]


async def _card_options(env: _Env) -> list[str]:
    """The model ids the channel ``/model`` card offers as buttons, from the same
    answer the card is built over (``suggest``)."""
    card = model_card(current=None, picks=await env.catalogue.suggest("claude_code"))
    return [b.value.removeprefix("model:") for b in card.buttons if b.value.startswith("model:")]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the agent's model picker offers a fixed list without free-form entry",
)
async def test_the_model_picker_offers_a_fixed_list_without_free_form_entry(env: _Env) -> None:
    """On the built-in login the picker offers the agent's own catalogue; once a
    connection overrides it, that connection's curated ``text`` ids — both served
    by the one route, and the channel ``/model`` card's buttons are exactly that
    list. Neither carries a free-text or "Custom…" entry, and the connection
    stores no model field of its own."""
    # Built-in login: the agent's own catalogue.
    assert [m["id"] for m in _models_route(env)] == _CLI_MODELS
    assert await _card_options(env) == _CLI_MODELS

    # A connection overrides it: its curated text ids, and not the non-text one.
    connection = await env.providers.create(
        "agnes",
        protocol=Protocol.OPENAI,
        base_url="https://agnes.example.test/v1",
        secret_value="sk-test",
        models=[
            CuratedModel(id="agnes-2.5-pro-beta"),
            CuratedModel(id="agnes-canvas-1", modality=Modality.IMAGE),
            CuratedModel(id="agnes-mini"),
        ],
    )
    await env.resources.update_scope(
        connection.uid, Scope(agents=[env.agent_uids[AgentType.CLAUDE_CODE]]), actor="test"
    )
    await env.providers.activate(connection.uid, AgentType.CLAUDE_CODE)

    models = _models_route(env)
    assert [m["id"] for m in models] == ["agnes-2.5-pro-beta", "agnes-mini"]
    assert await _card_options(env) == ["agnes-2.5-pro-beta", "agnes-mini"]
    # Each entry is an id with its label: nothing to type a model into.
    assert all(set(m) == {"id", "label", "description"} for m in models), models
    card = model_card(current=None, picks=await env.catalogue.suggest("claude_code"))
    assert all(b.value.startswith("model:") for b in card.buttons)
    assert not any("custom" in b.label.lower() for b in card.buttons)
    # The model lives on the agent's binding, never on the connection.
    stored = await env.resources.get(connection.uid)
    assert "model" not in stored.config
