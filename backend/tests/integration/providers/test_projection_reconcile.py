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
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.projection_reconcile import TARGET, ProviderProjectionTarget
from coffer.application.provider.projector import ProviderProjector
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
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from tests.support.facets import agent_catalog
from tests.support.homes import FakeAgentDir, IsolatedHome, fake_agent_dir

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


@dataclass
class _Env:
    providers: ProviderService
    reconciler: Reconciler
    audit: AuditService
    agent: FakeAgentDir
    connection_uid: str

    @property
    def settings(self) -> pathlib.Path:
        return self.agent.path("settings")

    async def repairs(self) -> list[tuple[str, str]]:
        rows = await self.audit.query(
            event_type=AuditEventType.PROVIDER_PROJECTION_REPAIRED.value, limit=50
        )
        return [(r.event_type, r.actor) for r in rows]

    async def is_active(self) -> bool:
        return bool((await self.providers.get(self.connection_uid)).config["is_active"])


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
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        secrets=store,
    )
    await resources.register(
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
            deactivate=providers.deactivate,
        )
    )
    conn_row = await providers.create(
        "acme", protocol=protocol, base_url=_BASE_URL, secret_value="sk-test-only", models=models
    )
    return _Env(providers, reconciler, audit, agent, conn_row.uid), engine


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
        # A command an older build wrote, or one a hand-edit changed: still
        # "present" to a presence test, and still not what Coffer writes now.
        ({"apiKeyHelper": "coffer provider key --connection-uid 0"}, "apiKeyHelper"),
    ],
    ids=["base_url", "api_key_helper"],
)
@pytest.mark.acceptance(
    spec="provider-switching", scenario="a projection whose values went stale is projected again"
)
async def test_a_projection_whose_parameters_drifted_is_repaired(
    env: _Env, edit: dict[str, object], param: str
) -> None:
    await env.providers.activate(env.connection_uid)
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
    scenario="boot clears an active flag the agent's config does not carry",
)
@pytest.mark.parametrize("trigger", [Trigger.BOOT, Trigger.PERIOD])
async def test_a_flag_the_agent_config_denies_is_cleared_and_the_file_untouched(
    env: _Env, trigger: Trigger
) -> None:
    await env.providers.activate(env.connection_uid)
    user_owned = json.dumps({"theme": "dark", "env": {"OTHER": "1"}}, indent=2) + "\n"
    env.settings.write_text(user_owned, encoding="utf-8")

    report = await env.reconciler.run(trigger=trigger)

    result = _only(report)
    assert result.change.decision.reason_code == "flag_contradicted"
    # Completes through ProviderService.deactivate, which takes the
    # reconciler's hold — re-entrant inside the pass, so no deadlock.
    assert result.outcome is Outcome.APPLIED
    assert await env.is_active() is False
    assert env.settings.read_text(encoding="utf-8") == user_owned
    assert await env.repairs() == []  # the switch audits itself


@pytest.mark.acceptance(
    spec="provider-switching", scenario="an import projects a switch made on another machine"
)
async def test_the_same_state_under_an_import_is_projected(env: _Env) -> None:
    """An import carried the user's explicit switch from another machine."""
    await env.providers.activate(env.connection_uid)
    env.settings.write_text("{}\n", encoding="utf-8")

    report = await env.reconciler.run(trigger=Trigger.IMPORT)

    result = _only(report)
    assert result.change.decision.reason_code == "projection_missing"
    assert result.outcome is Outcome.APPLIED
    assert await env.is_active() is True
    doc = json.loads(env.settings.read_text(encoding="utf-8"))
    # The agent is pointed at the local proxy with its own token helper; the
    # connection's endpoint stays with the proxy.
    assert doc["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8001/anthropic"
    assert " proxy token --agent-uid " in doc["apiKeyHelper"]
    assert await env.repairs() == [(AuditEventType.PROVIDER_PROJECTION_REPAIRED.value, "sync")]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="keys no active connection claims are reported, not removed"
)
async def test_keys_nothing_active_claims_are_reported_until_a_person_asks(env: _Env) -> None:
    await env.providers.activate(env.connection_uid)
    projected = env.settings.read_text(encoding="utf-8")
    # The flag goes, the keys stay (another tool restored the file, say).
    row = await env.providers.get(env.connection_uid)
    await env.providers._set_active(row, active=False, actor="test")

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
    await env.providers.activate(env.connection_uid)
    _edit_settings(env.settings, env__ANTHROPIC_BASE_URL="https://elsewhere.example/v1")
    drifted = env.settings.read_text(encoding="utf-8")

    report = await env.reconciler.plan(trigger=Trigger.PERIOD)

    assert _only(report).change.decision.reason_code == "projection_stale"
    assert _only(report).outcome is Outcome.PLANNED
    assert env.settings.read_text(encoding="utf-8") == drifted
    assert await env.repairs() == []
    assert await env.is_active() is True


async def test_a_file_that_does_not_parse_is_left_alone(env: _Env) -> None:
    await env.providers.activate(env.connection_uid)
    env.settings.write_text("{ not json", encoding="utf-8")

    report = await env.reconciler.run(trigger=Trigger.PERIOD)

    assert [r for r in report.results if r.change.difference.target == TARGET] == []
    assert env.settings.read_text(encoding="utf-8") == "{ not json"
    assert await env.is_active() is True


async def test_a_projection_in_step_is_no_difference(env: _Env) -> None:
    await env.providers.activate(env.connection_uid)

    assert (await env.reconciler.plan(trigger=Trigger.PERIOD)).results == ()


async def test_a_missing_model_catalogue_is_drift_and_is_rewritten(codex: _Env) -> None:
    await codex.providers.activate(codex.connection_uid)
    catalog = codex.agent.config_dir / CODEX_MODEL_CATALOG_FILENAME
    written = catalog.read_text(encoding="utf-8")
    catalog.unlink()

    report = await codex.reconciler.run(trigger=Trigger.PERIOD)

    result = _only(report)
    assert result.change.difference.changed_params == (f"file:{CODEX_MODEL_CATALOG_FILENAME}",)
    assert result.outcome is Outcome.APPLIED
    assert catalog.read_text(encoding="utf-8") == written


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a leftover shell exclude entry is not a Codex projection"
)
async def test_a_leftover_codex_shell_exclude_clears_the_flag(codex: _Env) -> None:
    await codex.providers.activate(codex.connection_uid)
    leftover = '[shell_environment_policy]\nexclude = ["COFFER_PROVIDER_KEY"]\n'
    config = codex.agent.path("config")
    config.write_text(leftover, encoding="utf-8")

    result = _only(await codex.reconciler.run(trigger=Trigger.BOOT))

    assert result.change.decision.reason_code == "flag_contradicted"
    assert result.outcome is Outcome.APPLIED
    assert await codex.is_active() is False


async def test_a_repair_whose_audit_fails_is_undone(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await env.providers.activate(env.connection_uid)
    _edit_settings(env.settings, env__ANTHROPIC_BASE_URL="https://elsewhere.example/v1")
    drifted = env.settings.read_text(encoding="utf-8")

    async def _refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit log unavailable")

    monkeypatch.setattr(env.audit, "record", _refuse)
    result = _only(await env.reconciler.run(trigger=Trigger.PERIOD))

    assert result.outcome is Outcome.FAILED
    assert env.settings.read_text(encoding="utf-8") == drifted


async def test_a_codex_projection_in_step_is_no_difference(codex: _Env) -> None:
    await codex.providers.activate(codex.connection_uid)

    assert (await codex.reconciler.plan(trigger=Trigger.PERIOD)).results == ()
