"""The internal engine's model belongs to the internal engine's connection.

Settings → Engine picks a connection and a model from two dropdowns, but the
model is a global singleton with no link to the connection. Switching the
connection used to leave the old connection's model standing — the user saw
"Agnes" paired with ``deepseek-flash`` — and Coffer's own background passes
then ran against a model the endpoint has never heard of.

Real ``ProviderService`` over a real SQLite file with the two model ports the
composition root wires, so the rule is exercised where it is enforced: in the
service, which is what BOTH the HTTP route and ``coffer provider
internal-default`` go through.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.service import ProviderService
from coffer.application.resource_service import ResourceService
from coffer.domain.provider.config import CuratedModel, Protocol
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo


class _DictStore:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self._d.get(ref)

    def set(self, ref: str, value: str) -> None:
        self._d[ref] = value

    def delete(self, ref: str) -> None:
        self._d.pop(ref, None)


class _NoAgents:
    async def list(self) -> list[Resource]:
        return []


class _ModelSingleton:
    """The internal-engine model singleton, narrowed to the two ports the
    provider service is given: read it, and forget it."""

    def __init__(self, model: str | None) -> None:
        self.model = model
        self.cleared_by: list[str] = []

    async def resolve(self) -> str | None:
        return self.model

    async def clear(self, actor: str) -> None:
        self.model = None
        self.cleared_by.append(actor)


class _Env:
    def __init__(self, providers: ProviderService, engine_model: _ModelSingleton) -> None:
        self.providers = providers
        self.engine_model = engine_model


async def _env(tmp_path: pathlib.Path, *, model: str | None, wire_clear: bool = True) -> _Env:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    # One store for both: the resource layer probes the very refs the provider
    # service mints, so a second store would report every key as missing.
    store = _DictStore()
    resources = ResourceService(
        kinds={"provider": make_provider_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        credentials=store,
    )
    singleton = _ModelSingleton(model)
    providers = ProviderService(
        resources=resources,
        credentials=store,
        config_store=ConfigFileStore(),
        agents=_NoAgents(),
        audit=audit,
        resolve_internal_model=singleton.resolve,
        clear_internal_model=singleton.clear if wire_clear else None,
    )
    return _Env(providers, singleton)


@pytest.fixture()
async def two_connections(tmp_path: pathlib.Path) -> AsyncIterator[_Env]:
    """``deepseek`` is the internal default and the singleton holds one of its
    models; ``agnes`` curates two models of its own, neither of them that one."""
    env = await _env(tmp_path, model="deepseek-flash")
    await env.providers.create(
        "deepseek",
        protocol=Protocol.OPENAI,
        base_url="https://deepseek.example",
        secret_value="k1",
        models=[CuratedModel(id="deepseek-flash")],
    )
    await env.providers.create(
        "agnes",
        protocol=Protocol.OPENAI,
        base_url="https://agnes.example",
        secret_value="k2",
        models=[CuratedModel(id="agnes-2.0-flash"), CuratedModel(id="agnes-1.5-flash")],
    )
    await env.providers.set_internal_default("deepseek")
    assert env.engine_model.model == "deepseek-flash", "deepseek curates the model in force"
    yield env


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="switching the internal engine's connection drops a model it does not serve",
)
async def test_switching_the_connection_drops_a_model_it_does_not_serve(
    two_connections: _Env,
) -> None:
    await two_connections.providers.set_internal_default("agnes", actor="cli")

    assert two_connections.engine_model.model is None, (
        "the new connection has never heard of deepseek-flash"
    )
    assert two_connections.engine_model.cleared_by == ["cli"]
    # Cleared, the internal engine is the documented clean no-op rather than a
    # pass aimed at a model the endpoint will reject.
    assert await two_connections.providers.resolve_internal_connection() is None


async def test_switching_keeps_a_model_the_new_connection_curates(two_connections: _Env) -> None:
    # The same id appears on agnes's curated list: its own catalogue says it is
    # servable, so the selection survives the switch without probing anything.
    await two_connections.providers.update("agnes", models=[CuratedModel(id="deepseek-flash")])

    await two_connections.providers.set_internal_default("agnes")

    assert two_connections.engine_model.model == "deepseek-flash"
    assert two_connections.engine_model.cleared_by == []
    resolved = await two_connections.providers.resolve_internal_connection()
    assert resolved is not None
    assert resolved.config.base_url == "https://agnes.example"
    assert resolved.model == "deepseek-flash"


async def test_re_setting_the_same_internal_default_changes_nothing(two_connections: _Env) -> None:
    await two_connections.providers.set_internal_default("deepseek")

    assert two_connections.engine_model.model == "deepseek-flash"
    assert two_connections.engine_model.cleared_by == []


async def test_the_model_is_untouched_when_no_clear_port_is_wired(
    tmp_path: pathlib.Path,
) -> None:
    """The ports are optional so a test may build the service without them;
    without one there is nothing to clear, and nothing is."""
    env = await _env(tmp_path, model="deepseek-flash", wire_clear=False)
    await env.providers.create(
        "agnes",
        protocol=Protocol.OPENAI,
        base_url="https://agnes.example",
        secret_value="k",
    )

    await env.providers.set_internal_default("agnes")

    assert env.engine_model.model == "deepseek-flash"
