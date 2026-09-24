"""The internal engine's model belongs to the internal engine's connection.

Settings → Coffer's model picks a connection and a model from two dropdowns, but the
model is a global singleton with no link to the connection. Switching the
connection used to leave the old connection's model standing — the user saw
"Agnes" paired with ``deepseek-flash`` — and Coffer's own background passes
then ran against a model the endpoint has never heard of.

Real ``ProviderService`` over a real SQLite file, wired to the real engine
guard and resolver the composition root ties, so the rule is exercised across
the seam it actually crosses: the provider kind reports the move, Coffer's own
engine (``application.engine``) decides the model's fate and answers what the
engine runs on. Both the HTTP route and ``coffer provider internal-default`` go
through this path.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.engine.internal_default import InternalDefaultModelGuard
from coffer.application.engine.resolve import InternalEngineConnection
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
    """``engine.internal_default.InternalEngineModelStore`` — the internal-engine
    model narrowed to what the engine does with it: read it, and forget it."""

    def __init__(self, model: str | None) -> None:
        self.model = model
        self.cleared_by: list[str] = []

    async def get_model(self) -> str | None:
        return self.model

    async def clear_model(self, *, actor: str) -> None:
        self.model = None
        self.cleared_by.append(actor)


class _Env:
    def __init__(
        self,
        providers: ProviderService,
        engine_model: _ModelSingleton,
        engine: InternalEngineConnection,
    ) -> None:
        self.providers = providers
        self.engine_model = engine_model
        # What every internal consumer asks: the connection Coffer's own engine
        # runs on. Not the provider service — that only says which row is
        # flagged (spec internal-engine "Resolve the engine's connection and model
        # together").
        self.engine = engine


async def _env(tmp_path: pathlib.Path, *, model: str | None, wire_engine: bool = True) -> _Env:
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
        engine=InternalDefaultModelGuard(singleton) if wire_engine else None,
    )
    return _Env(
        providers,
        singleton,
        InternalEngineConnection(read_model=singleton.get_model, connections=providers),
    )


async def _uid(env: _Env, name: str) -> str:
    """The uid of the connection labelled ``name``.

    These tests say "deepseek" because a person would; every call into the
    service takes the uid, because nothing inside the daemon addresses a
    resource by a label the user may change. Resolving it here is the same
    one-step lookup a surface does at its own front door.
    """
    for row in await env.providers.list():
        if row.name == name:
            return row.uid
    raise AssertionError(f"no connection named {name!r}")


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
    await env.providers.set_internal_default(await _uid(env, "deepseek"))
    assert env.engine_model.model == "deepseek-flash", "deepseek curates the model in force"
    yield env


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="switching the internal engine's connection drops a model it does not serve",
)
async def test_switching_the_connection_drops_a_model_it_does_not_serve(
    two_connections: _Env,
) -> None:
    await two_connections.providers.set_internal_default(
        await _uid(two_connections, "agnes"), actor="cli"
    )

    assert two_connections.engine_model.model is None, (
        "the new connection has never heard of deepseek-flash"
    )
    assert two_connections.engine_model.cleared_by == ["cli"]
    # Cleared, the internal engine is the documented clean no-op rather than a
    # pass aimed at a model the endpoint will reject.
    assert await two_connections.engine.get_default() is None


async def test_switching_keeps_a_model_the_new_connection_curates(two_connections: _Env) -> None:
    # The same id appears on agnes's curated list: its own catalogue says it is
    # servable, so the selection survives the switch without probing anything.
    await two_connections.providers.update(
        await _uid(two_connections, "agnes"), models=[CuratedModel(id="deepseek-flash")]
    )

    await two_connections.providers.set_internal_default(await _uid(two_connections, "agnes"))

    assert two_connections.engine_model.model == "deepseek-flash"
    assert two_connections.engine_model.cleared_by == []
    resolved = await two_connections.engine.get_default()
    assert resolved is not None
    assert resolved.config.base_url == "https://agnes.example"
    assert resolved.model == "deepseek-flash"


async def test_re_setting_the_same_internal_default_changes_nothing(two_connections: _Env) -> None:
    await two_connections.providers.set_internal_default(await _uid(two_connections, "deepseek"))

    assert two_connections.engine_model.model == "deepseek-flash"
    assert two_connections.engine_model.cleared_by == []


async def test_the_model_is_untouched_when_no_engine_port_is_wired(
    tmp_path: pathlib.Path,
) -> None:
    """The port is optional so a test may build the service without it; with no
    engine to tell, there is nothing to decide the model's fate, and nothing
    does."""
    env = await _env(tmp_path, model="deepseek-flash", wire_engine=False)
    await env.providers.create(
        "agnes",
        protocol=Protocol.OPENAI,
        base_url="https://agnes.example",
        secret_value="k",
    )

    await env.providers.set_internal_default(await _uid(env, "agnes"))

    assert env.engine_model.model == "deepseek-flash"


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="nothing configured makes every internal pass a clean no-op",
)
async def test_either_missing_half_answers_none_rather_than_raising(
    tmp_path: pathlib.Path,
) -> None:
    """Both halves are required, and a missing one is an answer, not a failure.

    No connection flagged `internal_default`, and a flagged connection with no
    model chosen, resolve to the same `None` — the pass that asked simply does
    not run, and nothing is raised for a caller to have to swallow.
    """
    # Half one: a model is chosen, but no connection is the internal default.
    (tmp_path / "a").mkdir()
    env = await _env(tmp_path / "a", model="deepseek-flash")
    await env.providers.create(
        "deepseek",
        protocol=Protocol.OPENAI,
        base_url="https://deepseek.example",
        secret_value="k1",
        models=[CuratedModel(id="deepseek-flash")],
    )
    assert await env.engine.get_default() is None

    # Half two: a connection is the internal default, but no model is chosen.
    (tmp_path / "b").mkdir()
    env2 = await _env(tmp_path / "b", model=None)
    await env2.providers.create(
        "deepseek",
        protocol=Protocol.OPENAI,
        base_url="https://deepseek.example",
        secret_value="k1",
        models=[CuratedModel(id="deepseek-flash")],
    )
    await env2.providers.set_internal_default(await _uid(env2, "deepseek"))
    assert await env2.engine.get_default() is None
