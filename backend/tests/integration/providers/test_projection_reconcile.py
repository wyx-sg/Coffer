"""The provider projection as a reconcile target, over real files and a real DB.

ADR one-level-triggered-reconciler-compares-parameters: the projection is
judged by every key Coffer owns in the agent's config, not by presence. These
drive real ``Reconciler`` passes over a real ``ProviderService`` (SQLite under
``tmp_path``) and an agent config tree laid out by ``fake_agent_dir``.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.provider import switch_ops
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.projection_reconcile import TARGET, ProviderProjectionTarget
from coffer.application.provider.projector import NativeModel, ProviderProjector
from coffer.application.provider.service import ProviderService
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.provider.config import CuratedModel, Protocol
from coffer.domain.provider.projection import CODEX_MODEL_CATALOG_FILENAME
from coffer.domain.reconcile import Disposition, ItemResult, Outcome, PassReport, Trigger
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from tests.support.facets import agent_catalog
from tests.support.homes import FakeAgentDir, IsolatedHome, fake_agent_dir
from tests.support.vault_stores import make_resource_repo

_BASE_URL = "https://gateway.example/v1"


class _DictStore:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self._d.get(ref)

    def set(self, ref: str, value: str) -> None:
        self._d[ref] = value

    def delete(self, ref: str) -> None:
        self._d.pop(ref, None)

    def exists(self, ref: str) -> bool:
        return ref in self._d


class _Agents:
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


@dataclass
class _Env:
    providers: ProviderService
    reconciler: Reconciler
    audit: AuditService
    agent: FakeAgentDir
    connection_uid: str
    agent_type: AgentType
    agent_uid: str
    agents: _Agents

    @property
    def settings(self) -> pathlib.Path:
        return self.agent.path("settings")

    async def repairs(self) -> list[tuple[str, str]]:
        rows = await self.audit.query(
            event_type=AuditEventType.PROVIDER_PROJECTION_REPAIRED.value, limit=50
        )
        return [(r.event_type, r.actor) for r in rows]

    async def switch(self) -> None:
        """Switch the agent onto the connection."""
        await self.providers.activate(self.connection_uid, self.agent_type)

    async def agent_connection(self) -> str | None:
        """The connection uid the agent's record names."""
        (row,) = await self.agents.list()
        value = row.config.get("connection_uid")
        return str(value) if value is not None else None


async def _build(
    tmp_path: pathlib.Path,
    home: IsolatedHome,
    agent_type: AgentType,
    protocol: Protocol,
    models: list[CuratedModel] | None = None,
) -> tuple[_Env, AsyncEngine]:
    agent = fake_agent_dir(home, agent_type)
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    store = _DictStore()
    resources = ResourceService(
        kinds={"provider": make_provider_kind(), "agent": make_agent_kind()},
        repo=make_resource_repo(),
        audit=audit,
        secrets=store,
    )
    registered = await resources.register(
        kind="agent",
        name=agent_type.default_name(),
        config={"type": agent_type.value, "config_dir": str(agent.config_dir)},
        actor="test",
        allow_lifecycle_kind=True,
    )
    reconciler = Reconciler(audit=audit)
    catalog = agent_catalog()
    agents = _Agents(resources)
    providers = ProviderService(
        agent_catalog=catalog,
        resources=resources,
        secrets=store,
        config_store=ConfigFileStore(),
        agents=agents,
        audit=audit,
        hold=reconciler.hold,
    )
    reconciler.register(
        ProviderProjectionTarget(
            providers=providers,
            agents=agents,
            projector=ProviderProjector(ConfigFileStore(), agents=catalog),
            store=ConfigFileStore(),
            clear_choice=providers.clear_agent_connection,
        )
    )
    conn_row = await providers.create(
        "acme", protocol=protocol, base_url=_BASE_URL, secret_value="sk-test-only", models=models
    )
    return (
        _Env(providers, reconciler, audit, agent, conn_row.uid, agent_type, registered.uid, agents),
        engine,
    )


@pytest.fixture()
async def env(tmp_path: pathlib.Path, isolated_home: IsolatedHome) -> AsyncIterator[_Env]:
    built, engine = await _build(tmp_path, isolated_home, AgentType.CLAUDE_CODE, Protocol.ANTHROPIC)
    yield built
    await engine.dispose()


@pytest.fixture()
async def codex(tmp_path: pathlib.Path, isolated_home: IsolatedHome) -> AsyncIterator[_Env]:
    built, engine = await _build(
        tmp_path,
        isolated_home,
        AgentType.CODEX,
        Protocol.OPENAI,
        models=[CuratedModel(id="m-1"), CuratedModel(id="m-2")],
    )
    yield built
    await engine.dispose()


def _only(report: PassReport) -> ItemResult:
    results = [r for r in report.results if r.change.difference.target == TARGET]
    assert len(results) == 1, results
    return results[0]


def _edit_settings(path: pathlib.Path, **changes: object) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for dotted, value in changes.items():
        *parents, leaf = dotted.split("__")
        node = doc
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = value
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("edit", "param"),
    [
        ({"env__ANTHROPIC_BASE_URL": "https://elsewhere.example/v1"}, "env.ANTHROPIC_BASE_URL"),
        # A command a hand-edit changed: still "present" to a presence test,
        # and still not what Coffer writes now.
        ({"apiKeyHelper": "coffer proxy token --agent-uid 0"}, "apiKeyHelper"),
    ],
    ids=["base_url", "api_key_helper"],
)
@pytest.mark.acceptance(
    spec="provider-switching", scenario="a projection whose values went stale is projected again"
)
async def test_a_projection_whose_parameters_drifted_is_repaired(
    env: _Env, edit: dict[str, object], param: str
) -> None:
    await env.switch()
    projected = env.settings.read_text(encoding="utf-8")
    _edit_settings(env.settings, **edit)

    report = await env.reconciler.run(trigger=Trigger.PERIOD)

    result = _only(report)
    assert result.change.difference.op.value == "modify"
    assert param in result.change.difference.changed_params
    assert result.change.decision.reason_code == "projection_stale"
    assert result.outcome is Outcome.APPLIED
    assert json.loads(env.settings.read_text(encoding="utf-8")) == json.loads(projected)
    assert await env.repairs() == [(AuditEventType.PROVIDER_PROJECTION_REPAIRED.value, "system")]
    # Converged: the next pass finds nothing.
    assert (await env.reconciler.run(trigger=Trigger.PERIOD)).results == ()


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="boot clears a connection the agent's config does not carry",
)
@pytest.mark.parametrize("trigger", [Trigger.BOOT, Trigger.PERIOD])
async def test_a_connection_the_agent_config_denies_is_cleared_and_the_file_untouched(
    env: _Env, trigger: Trigger
) -> None:
    await env.switch()
    user_owned = json.dumps({"theme": "dark", "env": {"OTHER": "1"}}, indent=2) + "\n"
    env.settings.write_text(user_owned, encoding="utf-8")

    report = await env.reconciler.run(trigger=trigger)

    result = _only(report)
    assert result.change.decision.reason_code == "choice_contradicted"
    # Completes through ProviderService.clear_agent_connection, which takes the
    # reconciler's hold — re-entrant inside the pass, so no deadlock.
    assert result.outcome is Outcome.APPLIED
    assert await env.agent_connection() is None
    assert env.settings.read_text(encoding="utf-8") == user_owned
    # The pass audits its own repair, as the system, not as an API caller.
    assert await env.repairs() == [(AuditEventType.PROVIDER_PROJECTION_REPAIRED.value, "system")]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an import re-projects an edited connection into the agent that runs on it",
)
async def test_the_same_state_under_an_import_is_projected(env: _Env) -> None:
    """A sync round's import warrants re-projecting an agent that runs on a
    connection: the keys gone from its file are written back."""
    await env.switch()
    env.settings.write_text("{}\n", encoding="utf-8")

    report = await env.reconciler.run(trigger=Trigger.IMPORT)

    result = _only(report)
    assert result.change.decision.reason_code == "projection_missing"
    assert result.outcome is Outcome.APPLIED
    assert await env.agent_connection() == env.connection_uid
    doc = json.loads(env.settings.read_text(encoding="utf-8"))
    # The agent is pointed at the local proxy with its own token helper; the
    # connection's endpoint stays with the proxy.
    assert doc["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:38471/anthropic"
    assert " proxy token --agent-uid " in doc["apiKeyHelper"]
    assert await env.repairs() == [(AuditEventType.PROVIDER_PROJECTION_REPAIRED.value, "sync")]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="keys no connection claims are reported, not removed"
)
async def test_keys_no_connection_claims_are_reported_until_a_person_asks(env: _Env) -> None:
    await env.switch()
    projected = env.settings.read_text(encoding="utf-8")
    # The choice goes, the keys stay (another tool restored the file, say).
    await env.providers.clear_agent_connection(env.agent_uid, actor="test")

    report = await env.reconciler.run(trigger=Trigger.PERIOD)

    result = _only(report)
    assert result.change.decision.disposition is Disposition.REPORT
    assert result.change.decision.reason_code == "projection_unclaimed"
    assert result.outcome is Outcome.PLANNED
    assert env.settings.read_text(encoding="utf-8") == projected

    manual = await env.reconciler.apply([result.change.id], actor="api")

    assert _only(manual).outcome is Outcome.APPLIED
    doc = json.loads(env.settings.read_text(encoding="utf-8"))
    assert "apiKeyHelper" not in doc
    assert "ANTHROPIC_BASE_URL" not in doc.get("env", {})
    assert await env.repairs() == [(AuditEventType.PROVIDER_PROJECTION_REPAIRED.value, "api")]


async def test_a_dry_run_writes_nothing(env: _Env) -> None:
    await env.switch()
    _edit_settings(env.settings, env__ANTHROPIC_BASE_URL="https://elsewhere.example/v1")
    drifted = env.settings.read_text(encoding="utf-8")

    report = await env.reconciler.plan(trigger=Trigger.PERIOD)

    assert _only(report).change.decision.reason_code == "projection_stale"
    assert _only(report).outcome is Outcome.PLANNED
    assert env.settings.read_text(encoding="utf-8") == drifted
    assert await env.repairs() == []
    assert await env.agent_connection() == env.connection_uid


async def test_a_file_that_does_not_parse_is_left_alone(env: _Env) -> None:
    await env.switch()
    env.settings.write_text("{ not json", encoding="utf-8")

    report = await env.reconciler.run(trigger=Trigger.PERIOD)

    assert [r for r in report.results if r.change.difference.target == TARGET] == []
    assert env.settings.read_text(encoding="utf-8") == "{ not json"
    assert await env.agent_connection() == env.connection_uid


async def test_a_projection_in_step_is_no_difference(env: _Env) -> None:
    await env.switch()

    assert (await env.reconciler.plan(trigger=Trigger.PERIOD)).results == ()


async def test_a_missing_model_catalogue_is_drift_and_is_rewritten(codex: _Env) -> None:
    await codex.switch()
    catalog = codex.agent.config_dir / CODEX_MODEL_CATALOG_FILENAME
    written = catalog.read_text(encoding="utf-8")
    catalog.unlink()

    report = await codex.reconciler.run(trigger=Trigger.PERIOD)

    result = _only(report)
    assert result.change.difference.changed_params == (f"file:{CODEX_MODEL_CATALOG_FILENAME}",)
    assert result.outcome is Outcome.APPLIED
    assert catalog.read_text(encoding="utf-8") == written


async def test_a_repair_whose_audit_fails_is_undone(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await env.switch()
    _edit_settings(env.settings, env__ANTHROPIC_BASE_URL="https://elsewhere.example/v1")
    drifted = env.settings.read_text(encoding="utf-8")

    async def _refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit log unavailable")

    monkeypatch.setattr(env.audit, "record", _refuse)
    result = _only(await env.reconciler.run(trigger=Trigger.PERIOD))

    assert result.outcome is Outcome.FAILED
    assert env.settings.read_text(encoding="utf-8") == drifted


async def test_a_codex_projection_in_step_is_no_difference(codex: _Env) -> None:
    await codex.switch()

    assert (await codex.reconciler.plan(trigger=Trigger.PERIOD)).results == ()


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the Codex auth table carries a timeout so a cold token command is not cut off",
)
async def test_a_codex_auth_table_without_a_timeout_is_re_projected(codex: _Env) -> None:
    await codex.switch()
    config = codex.agent.path("config")
    current = config.read_text(encoding="utf-8")
    assert "timeout_ms = 30000" in current
    config.write_text(current.replace(", timeout_ms = 30000", ""), encoding="utf-8")

    result = _only(await codex.reconciler.run(trigger=Trigger.PERIOD))

    assert result.outcome is Outcome.APPLIED
    assert any(p.endswith("auth.timeout_ms") for p in result.change.difference.changed_params)
    assert config.read_text(encoding="utf-8") == current


async def _built_in_model_survives(built: _Env, key: str) -> None:
    await built.switch()
    await switch_ops.deactivate(
        built.providers, built.agent_type, actor="test", native_model=NativeModel("own-model")
    )
    path = built.agent.path(key)
    before = path.read_text(encoding="utf-8")
    assert "own-model" in before

    assert (await built.reconciler.plan(trigger=Trigger.PERIOD)).results == ()
    # Even a pass a person asked for (the one that removes unclaimed keys).
    assert (await built.reconciler.run(trigger=Trigger.MANUAL)).results == ()
    assert path.read_text(encoding="utf-8") == before


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a model set on the built-in login is not Coffer's to report or remove",
)
async def test_a_claude_code_model_set_on_the_built_in_login_survives_a_pass(env: _Env) -> None:
    await _built_in_model_survives(env, "settings")


async def test_a_codex_model_set_on_the_built_in_login_survives_a_pass(codex: _Env) -> None:
    await _built_in_model_survives(codex, "config")
