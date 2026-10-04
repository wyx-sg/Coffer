"""The speech-to-text model belongs to the speech-to-text connection.

Settings, General, picks a connection and a model, but the model is a global
singleton with no link to the connection. Switching the connection must not
leave the old connection's model standing: the next voice message would aim at
a model the endpoint has never heard of.

Real ``ProviderService`` over a real SQLite file, wired to the real engine guard
and resolver the composition root ties, so the rule is exercised across the seam
it actually crosses: the provider kind reports the move, Coffer's engine
(``application.engine``) decides the model's fate and answers what transcription
runs on.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.engine.internal_default import InternalDefaultModelGuard
from coffer.application.engine.resolve import resolve_transcribe_connection
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.service import ProviderService
from coffer.application.resource_service import ResourceService
from coffer.domain.provider.config import CuratedModel, Protocol, ResolvedConnection
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from tests.support.facets import agent_catalog
from tests.support.vault_stores import make_resource_repo


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
    """``engine.internal_default.InternalEngineModelStore`` — the speech-to-text
    model narrowed to what the engine does with it: read it, and forget it."""

    def __init__(self, model: str | None) -> None:
        self.model = model
        self.cleared_by: list[str] = []

    async def get_transcribe_model(self) -> str | None:
        return self.model

    async def clear_transcribe_model(self, *, actor: str) -> None:
        self.model = None
        self.cleared_by.append(actor)


class _Env:
    def __init__(self, providers: ProviderService, engine_model: _ModelSingleton) -> None:
        self.providers = providers
        self.engine_model = engine_model

    async def transcribe_connection(self) -> ResolvedConnection | None:
        """What voice transcription asks: the flagged connection paired with
        the chosen model, or ``None`` for either missing half."""
        return await resolve_transcribe_connection(
            read_model=self.engine_model.get_transcribe_model, connections=self.providers
        )


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
        repo=make_resource_repo(home=tmp_path),
        audit=audit,
        secrets=store,
    )
    singleton = _ModelSingleton(model)
    providers = ProviderService(
        agent_catalog=agent_catalog(),
        resources=resources,
        secrets=store,
        config_store=ConfigFileStore(),
        agents=_NoAgents(),
        audit=audit,
        engine=InternalDefaultModelGuard(singleton) if wire_engine else None,
    )
    return _Env(providers, singleton)


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
    """``deepseek`` is the speech-to-text connection and the singleton holds one
    of its models; ``agnes`` curates two models of its own, neither of them that
    one."""
    env = await _env(tmp_path, model="whisper-1")
    await env.providers.create(
        "deepseek",
        protocol=Protocol.OPENAI,
        base_url="https://deepseek.example",
        secret_value="k1",
        models=[CuratedModel(id="whisper-1")],
    )
    await env.providers.create(
        "agnes",
        protocol=Protocol.OPENAI,
        base_url="https://agnes.example",
        secret_value="k2",
        models=[CuratedModel(id="agnes-asr"), CuratedModel(id="agnes-asr-2")],
    )
    await env.providers.set_transcribe_default(await _uid(env, "deepseek"))
    assert env.engine_model.model == "whisper-1", "deepseek curates the model in force"
    yield env


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="speech-to-text runs on its own connection and its own model",
)
async def test_switching_the_connection_drops_a_model_it_does_not_serve(
    two_connections: _Env,
) -> None:
    await two_connections.providers.set_transcribe_default(
        await _uid(two_connections, "agnes"), actor="cli"
    )

    assert two_connections.engine_model.model is None, (
        "the new connection has never heard of whisper-1"
    )
    assert two_connections.engine_model.cleared_by == ["cli"]
    # Cleared, transcription is the documented clean no-op rather than a request
    # aimed at a model the endpoint will reject.
    assert await two_connections.transcribe_connection() is None


async def test_switching_keeps_a_model_the_new_connection_curates(two_connections: _Env) -> None:
    # The same id appears on agnes's curated list: its own catalogue says it is
    # servable, so the selection survives the switch without probing anything.
    await two_connections.providers.update(
        await _uid(two_connections, "agnes"), models=[CuratedModel(id="whisper-1")]
    )

    await two_connections.providers.set_transcribe_default(await _uid(two_connections, "agnes"))

    assert two_connections.engine_model.model == "whisper-1"
    assert two_connections.engine_model.cleared_by == []
    resolved = await two_connections.transcribe_connection()
    assert resolved is not None
    assert resolved.config.base_url == "https://agnes.example"
    assert resolved.model == "whisper-1"


async def test_re_setting_the_same_default_changes_nothing(two_connections: _Env) -> None:
    await two_connections.providers.set_transcribe_default(await _uid(two_connections, "deepseek"))

    assert two_connections.engine_model.model == "whisper-1"
    assert two_connections.engine_model.cleared_by == []


async def test_the_model_is_untouched_when_no_engine_port_is_wired(
    tmp_path: pathlib.Path,
) -> None:
    """The port is optional so a test may build the service without it; with no
    engine to tell, there is nothing to decide the model's fate, and nothing
    does."""
    env = await _env(tmp_path, model="whisper-1", wire_engine=False)
    await env.providers.create(
        "agnes",
        protocol=Protocol.OPENAI,
        base_url="https://agnes.example",
        secret_value="k",
    )

    await env.providers.set_transcribe_default(await _uid(env, "agnes"))

    assert env.engine_model.model == "whisper-1"


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="speech-to-text runs on its own connection and its own model",
)
async def test_either_missing_half_answers_none_rather_than_raising(
    tmp_path: pathlib.Path,
) -> None:
    """Both halves are required, and a missing one is an answer, not a failure."""
    # Half one: a model is chosen, but no connection is flagged.
    (tmp_path / "a").mkdir()
    env = await _env(tmp_path / "a", model="whisper-1")
    await env.providers.create(
        "deepseek",
        protocol=Protocol.OPENAI,
        base_url="https://deepseek.example",
        secret_value="k1",
        models=[CuratedModel(id="whisper-1")],
    )
    assert await env.transcribe_connection() is None

    # Half two: a connection is flagged, but no model is chosen.
    (tmp_path / "b").mkdir()
    env2 = await _env(tmp_path / "b", model=None)
    await env2.providers.create(
        "deepseek",
        protocol=Protocol.OPENAI,
        base_url="https://deepseek.example",
        secret_value="k1",
        models=[CuratedModel(id="whisper-1")],
    )
    await env2.providers.set_transcribe_default(await _uid(env2, "deepseek"))
    assert await env2.transcribe_connection() is None
