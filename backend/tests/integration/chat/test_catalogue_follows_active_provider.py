"""The model catalogue follows the provider Coffer activated for the agent.

Real ``ProviderService`` over a real SQLite file, the real composition-root
adapter (``_ActiveProviderModels``), and the real on-disk discovery source, so
the whole chain the bug ran through is exercised: register an openai-compatible
gateway, route it at Claude Code, activate it — and the catalogue must stop
offering models only the CLI's own login can serve.

The regression it guards: the channel ``/model`` card offered ``claude-opus-5``
while every turn went to a gateway that has never heard of it, so tapping it
failed the turn at the SDK.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from collections.abc import AsyncIterator

import pytest

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.audit_service import AuditService
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.service import ProviderService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import CuratedModel, Protocol
from coffer.domain.provider.modality import Modality
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.agent.model_discovery import NativeConfigModelDiscovery
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.surfaces.http.dependencies import set_provider_service
from coffer.surfaces.http.wiring import _ActiveProviderModels

_NOW = dt.datetime(2026, 9, 11, tzinfo=dt.UTC)

#: What the CLI's own login can run, as Claude Code caches it on disk.
_CLI_MODELS = ["claude-opus-5", "claude-sonnet-5"]

#: What the user ticked on the gateway's detail page. Both are CHAT models —
#: the second's name notwithstanding, because a curated entry's modality is
#: STORED, never read back out of its id.
_GATEWAY_MODELS = ["agnes-2.5-pro-beta", "agnes-video-2.5"]


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


class _FakeAgents:
    """The agent registry, narrowed to what both services ask of it."""

    def __init__(self, resources: list[Resource]) -> None:
        self._resources = resources

    async def list(self) -> list[Resource]:
        return list(self._resources)


def _agent_resource(config_dir: pathlib.Path, agent_type: str) -> Resource:
    return Resource(
        id=1,
        kind="agent",
        name=agent_type,
        description=None,
        config={"type": agent_type, "config_dir": str(config_dir)},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _Env:
    def __init__(self, providers: ProviderService, catalogue: AgentModelCatalogueService) -> None:
        self.providers = providers
        self.catalogue = catalogue


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
    agents = _FakeAgents([_agent_resource(config_dir, "claude_code")])
    providers = ProviderService(
        resources=ResourceService(
            kinds={"provider": make_provider_kind()},
            repo=SqlAlchemyResourceRepo(sm),
            audit=audit,
            credentials=store,
        ),
        credentials=store,
        config_store=ConfigFileStore(),
        agents=_FakeAgents([]),  # nothing to project into: this test reads, not writes
        audit=audit,
    )
    set_provider_service(providers)
    yield _Env(
        providers,
        AgentModelCatalogueService(
            agents=agents,
            discovery=NativeConfigModelDiscovery(),
            provider_models=_ActiveProviderModels(),
        ),
    )
    set_provider_service(None)
    await engine.dispose()


async def _gateway(
    env: _Env, *, models: list[CuratedModel], agents: list[AgentType], name: str = "agnes"
) -> None:
    await env.providers.create(
        name,
        protocol=Protocol.OPENAI,
        base_url="https://agnes.example.test/v1",
        secret_value="sk-test",
        compatible_agents=agents,
        models=models,
    )
    await env.providers.activate(name)


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
