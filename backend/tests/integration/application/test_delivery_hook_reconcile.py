"""The delivery-hook reconcile target on real files, a real database and a
real ``Reconciler`` (ADR one-level-triggered-reconciler-compares-parameters).

Every test runs under an isolated HOME: the agents' config trees are laid out
by ``fake_agent_dir`` from their own descriptors, the database sits at the
home's ``~/.coffer/runs.db``, and "connected" is the real answer — the agent
carries Coffer's gateway MCP entry, installed by ``AgentMcpService``.

- A stale hook — a bare ``coffer`` command on ``SessionStart`` alone — is
  found as a MODIFY of ``command`` and ``event`` and rewritten into this
  build's two entries, foreign hooks untouched, one audit row from
  ``system`` (spec memory "Repair stale delivery hooks"). For Codex the
  rewritten entries are then reported as needing the user's approval in Codex
  until ``config.toml`` records each of them.
- An audit that cannot be recorded puts the file back as it was.
- A dry-run writes nothing anywhere under HOME, nor any row, nor any of the
  reconciler's own bookkeeping.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.service import AgentService
from coffer.application.attention import Severity
from coffer.application.audit_service import AuditService
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.delivery_reconcile import TARGET, DeliveryHookTarget
from coffer.application.reconcile.attention_source import APPLY_PATH, DriftAttentionSource
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.delivery import DELIVERY_EVENTS, MARKER, DeliveryAdapter
from coffer.domain.reconcile import Disposition, Op, Outcome, Trigger
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.memory.delivery.codex import current_hash, trust_key
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.platform import HostPlatform
from tests.support.facets import TEST_COFFER_CLI, agent_catalog
from tests.support.homes import FakeAgentDir, IsolatedHome, fake_agent_dir
from tests.support.vault_stores import make_resource_repo

pytestmark = pytest.mark.asyncio

_SHIM = "/opt/coffer/coffer-mcp-shim"

#: Hooks another tool wired up, which no pass may touch.
_FOREIGN_SESSION = {"hooks": [{"type": "command", "command": "/skynet/sessionStart.sh"}]}
_FOREIGN_STOP = {"hooks": [{"type": "command", "command": "/skynet/stop.sh"}]}


class _MemoryOn:
    def is_enabled(self, key: str) -> bool:
        return key == "memory"


@dataclass
class _Rig:
    home: IsolatedHome
    agents: AgentService
    mcp: AgentMcpService
    delivery: DeliveryService
    audit: AuditService
    repo: SqlAlchemyAuditRepo
    reconciler: Reconciler
    engine: object

    async def connected(self) -> list[str]:
        out = []
        for row in await self.agents.list():
            if (await self.mcp.status(row.uid)).installed:
                out.append(row.uid)
        return out

    async def audit_count(self) -> int:
        async with self.engine.connect() as conn:  # type: ignore[attr-defined]
            return int((await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar_one())


@pytest_asyncio.fixture
async def rig(isolated_home: IsolatedHome) -> AsyncIterator[_Rig]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{isolated_home.db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    repo = SqlAlchemyAuditRepo(sm)
    audit = AuditService(repo)
    rs = ResourceService(
        kinds={"agent": make_agent_kind(on_delete=None)},
        repo=make_resource_repo(),
        audit=audit,
    )
    store = ConfigFileStore()
    agents = AgentService(
        platform=HostPlatform(), resource_service=rs, audit=audit, config_file_store=store
    )
    mcp = AgentMcpService(
        agent_service=agents, audit=audit, store=store, shim_resolver=lambda: _SHIM
    )
    delivery = DeliveryService(
        agent_service=agents, audit=audit, store=store, catalog=agent_catalog()
    )
    reconciler = Reconciler(audit=audit)
    built = _Rig(isolated_home, agents, mcp, delivery, audit, repo, reconciler, engine)
    reconciler.register(
        DeliveryHookTarget(delivery=delivery, features=_MemoryOn(), connected=built.connected)
    )
    try:
        yield built
    finally:
        await engine.dispose()


def _approve_in_codex(hooks: pathlib.Path, config: pathlib.Path, adapter: DeliveryAdapter) -> None:
    """What the user's approval in Codex's /hooks records in config.toml: one
    record per entry."""
    found = adapter.find_all(hooks.read_text())
    assert len(found) == len(DELIVERY_EVENTS)
    approvals = "".join(
        f'\n[hooks.state."{trust_key(str(hooks), hook)}"]\ntrusted_hash = "{current_hash(hook)}"\n'
        for hook in found
    )
    config.write_text(config.read_text() + approvals)


async def _connected_agent_with_stale_hook(
    rig: _Rig, agent_type: AgentType
) -> tuple[Resource, FakeAgentDir, pathlib.Path]:
    """An agent connected to Coffer whose settings file carries Coffer's hook
    with a stale command on one event, beside foreign hooks on the same and
    other events."""
    agent_dir = fake_agent_dir(rig.home, agent_type)
    agent = await rig.agents.register(agent_type=agent_type, actor="cli")
    await rig.mcp.install(agent.uid, actor="ui")
    adapter = agent_catalog().delivery_hook(agent_type)
    assert adapter is not None
    key = "settings" if agent_type is AgentType.CLAUDE_CODE else "hooks"
    # Bare `coffer` (not on the hook's PATH), and on one event only.
    stale = f': {MARKER}; coffer memory hook --agent-uid {agent.uid} --cwd "$PWD"'
    stale_event = "SessionStart"
    leaf = {"type": "command", "command": stale}
    doc = {
        "theme": "dark",
        "hooks": {
            stale_event: [_FOREIGN_SESSION, {"hooks": [leaf]}],
            "Stop": [_FOREIGN_STOP],
        },
    }
    path = agent_dir.write(key, json.dumps(doc, indent=2))
    assert (
        rig.delivery.installed_command(
            next(s for s in await rig.delivery.sites() if s.agent.uid == agent.uid)
        )
        == stale
    )
    return agent, agent_dir, path


@pytest.mark.acceptance(
    spec="memory",
    scenario="a hook whose command went stale is repaired without being asked",
)
@pytest.mark.parametrize("agent_type", [AgentType.CLAUDE_CODE, AgentType.CODEX])
async def test_a_stale_hook_is_rewritten_into_the_current_entries(
    rig: _Rig, agent_type: AgentType
) -> None:
    agent, _dir, path = await _connected_agent_with_stale_hook(rig, agent_type)
    adapter = agent_catalog().delivery_hook(agent_type)
    assert adapter is not None

    plan = await rig.reconciler.plan(targets=[TARGET], trigger=Trigger.PERIOD)
    (planned,) = plan.results
    assert planned.change.difference.op is Op.MODIFY
    expected_changes = (
        ("command", "event")
        if agent_type is AgentType.CLAUDE_CODE
        else ("command", "event", "trust")
    )
    assert planned.change.difference.changed_params == expected_changes
    assert planned.change.decision.disposition is Disposition.REPAIR
    assert planned.change.decision.reason_code == "stale_command"

    report = await rig.reconciler.run(trigger=Trigger.PERIOD)

    (result,) = report.results
    assert result.outcome is Outcome.APPLIED
    data = json.loads(path.read_text())
    assert data["theme"] == "dark"
    assert data["hooks"]["Stop"] == [_FOREIGN_STOP]
    assert _FOREIGN_SESSION in data["hooks"]["SessionStart"]
    coffer_commands = [
        (event, leaf["command"])
        for event, groups in data["hooks"].items()
        for g in groups
        for leaf in g["hooks"]
        if MARKER in leaf["command"]
    ]
    # One entry on each of the two events, every one the current command.
    assert sorted(coffer_commands) == sorted(
        (event, adapter.command_for(agent.uid)) for event in DELIVERY_EVENTS
    )
    # By absolute path: the hook's shell need not have ~/.coffer/bin on PATH.
    assert adapter.command_for(agent.uid).startswith(f": {MARKER}; {TEST_COFFER_CLI} ")
    assert ConfigFileStore().latest_backup(path) is not None
    assert not path.with_name(path.name + ".bak").exists()

    rows = await rig.audit.query(
        resource=agent, event_type=AuditEventType.MEMORY_DELIVERY_INSTALLED.value
    )
    assert len(rows) == 1
    assert rows[0].actor == "system"
    assert rows[0].details["path"] == str(path)
    assert rows[0].details["reason"] == "stale_command"

    if agent_type is AgentType.CODEX:
        # The rewritten hook needs the user's approval in Codex before Codex
        # runs it: reported every pass, never approved by Coffer.
        (untrusted,) = (await rig.reconciler.run(trigger=Trigger.PERIOD)).results
        assert untrusted.change.decision.reason_code == "hook_untrusted"
        assert untrusted.outcome is Outcome.PLANNED
        config = _dir.path("config")
        assert "hooks.state" not in config.read_text()  # Coffer wrote no trust
        _approve_in_codex(path, config, adapter)

    # Converged: the next pass finds nothing to do.
    assert (await rig.reconciler.run(trigger=Trigger.PERIOD)).results == ()


async def test_an_audit_that_cannot_be_recorded_puts_the_file_back(
    rig: _Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    _agent, _dir, path = await _connected_agent_with_stale_hook(rig, AgentType.CLAUDE_CODE)
    before = path.read_text()

    async def _refuse(entry: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(rig.repo, "insert", _refuse)
    report = await rig.reconciler.run(trigger=Trigger.PERIOD)

    (result,) = report.results
    assert result.outcome is Outcome.FAILED
    assert "audit not recorded" in (result.error or "")
    assert path.read_text() == before


@pytest.mark.acceptance(
    spec="memory",
    scenario="a four-entry hook is rewritten to two without losing Codex's approvals",
)
@pytest.mark.parametrize("agent_type", [AgentType.CLAUDE_CODE, AgentType.CODEX])
async def test_a_four_entry_hook_is_rewritten_to_two(rig: _Rig, agent_type: AgentType) -> None:
    agent_dir = fake_agent_dir(rig.home, agent_type)
    agent = await rig.agents.register(agent_type=agent_type, actor="cli")
    await rig.mcp.install(agent.uid, actor="ui")
    adapter = agent_catalog().delivery_hook(agent_type)
    assert adapter is not None
    command = adapter.command_for(agent.uid)

    def entry(matcher: str | None, timeout: int) -> dict[str, object]:
        group: dict[str, object] = {"hooks": [{"type": "command", "command": command}]}
        group["hooks"][0]["timeout"] = timeout  # type: ignore[index]
        if matcher is not None:
            group["matcher"] = matcher
        return group

    foreign_pre = {"hooks": [{"type": "command", "command": "/skynet/beforeShell.sh"}]}
    doc = {
        "hooks": {
            "SessionStart": [_FOREIGN_SESSION, entry("startup|resume|clear|compact", 10)],
            "UserPromptSubmit": [entry(None, 5)],
            "PreToolUse": [foreign_pre, entry("Bash", 5)],
            "PostToolUse": [entry("Bash", 5)],
        }
    }
    key = "settings" if agent_type is AgentType.CLAUDE_CODE else "hooks"
    path = agent_dir.write(key, json.dumps(doc, indent=2))
    four = adapter.find_all(path.read_text())
    assert len(four) == 4
    trust_before: dict[str, str] = {}
    if agent_type is AgentType.CODEX:
        config = agent_dir.path("config")
        config.write_text(
            config.read_text()
            + "".join(
                f'\n[hooks.state."{trust_key(str(path), h)}"]\ntrusted_hash = "{current_hash(h)}"\n'
                for h in four
            )
        )
        trust_before = {trust_key(str(path), h): current_hash(h) for h in four}
        config_before = config.read_text()

    plan = await rig.reconciler.plan(targets=[TARGET], trigger=Trigger.PERIOD)
    (planned,) = plan.results
    assert planned.change.difference.op is Op.MODIFY
    assert "event" in planned.change.difference.changed_params
    assert "command" not in planned.change.difference.changed_params

    (result,) = (await rig.reconciler.run(trigger=Trigger.PERIOD)).results
    assert result.outcome is Outcome.APPLIED

    data = json.loads(path.read_text())
    two = adapter.find_all(path.read_text())
    assert sorted(h.event for h in two) == ["SessionStart", "UserPromptSubmit"]
    assert [h.command for h in two] == [command, command]
    # A foreign hook on a shell event stays; Coffer's entries on them are gone.
    assert data["hooks"]["PreToolUse"] == [foreign_pre]
    assert "PostToolUse" not in data["hooks"]
    assert data["hooks"]["SessionStart"][0] == _FOREIGN_SESSION

    if agent_type is AgentType.CODEX:
        # The two kept entries keep their position and command, so the keys and
        # hashes Codex recorded for them still match; Coffer wrote no approval.
        for h in two:
            k = trust_key(str(path), h)
            assert trust_before[k] == current_hash(h)
        assert config.read_text() == config_before
    # Converged: no `hook_untrusted` either, the approvals still match.
    assert (await rig.reconciler.run(trigger=Trigger.PERIOD)).results == ()


def _fingerprint(root: pathlib.Path) -> dict[str, tuple[int, str, int]]:
    out: dict[str, tuple[int, str, int]] = {}
    for p in sorted(root.rglob("*")):
        # SQLite's ``-shm`` is the WAL index every *reader* updates: a read of
        # runs.db touches it without writing anything.
        if p.is_file() and not p.is_symlink() and not p.name.endswith("-shm"):
            st = p.stat()
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            out[str(p.relative_to(root))] = (st.st_size, digest, st.st_mtime_ns)
    return out


async def test_a_dry_run_writes_nothing_under_home(rig: _Rig) -> None:
    await _connected_agent_with_stale_hook(rig, AgentType.CLAUDE_CODE)
    await _connected_agent_with_stale_hook(rig, AgentType.CODEX)
    assert rig.home.db_path.is_file()
    files_before = _fingerprint(rig.home.root)
    rows_before = await rig.audit_count()

    plan = await rig.reconciler.plan()

    assert _fingerprint(rig.home.root) == files_before
    assert await rig.audit_count() == rows_before
    assert plan.dry_run is True
    assert [r.change.difference.op for r in plan.results] == [Op.MODIFY, Op.MODIFY]
    assert all(r.outcome is Outcome.PLANNED for r in plan.results)
    assert not rig.reconciler.pending_hints
    assert rig.reconciler.last_pass is None


@pytest.mark.acceptance(
    spec="web-ui",
    scenario="a memory hook changed by hand that coffer could not rewrite needs the user",
)
async def test_a_hand_edited_hook_a_pass_cannot_rewrite_is_a_needs_you_item(
    rig: _Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Overview's Needs-you row for a hook changed by hand is the reconciler
    drift source's item: absent while the next pass would simply rewrite the
    hook, present — on the agent, with Repair — once a pass tried and failed."""
    agent, _dir, _path = await _connected_agent_with_stale_hook(rig, AgentType.CLAUDE_CODE)
    source = DriftAttentionSource(rig.reconciler)
    # No pass has visited it yet: the next one rewrites it without anyone.
    assert await source.items() == []

    async def _refuse(entry: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(rig.repo, "insert", _refuse)
    (result,) = (await rig.reconciler.run(trigger=Trigger.PERIOD)).results
    assert result.outcome is Outcome.FAILED

    (item,) = await source.items()
    assert (item.kind, item.uid, item.reason_code) == ("agent", agent.uid, "stale_command")
    assert item.severity is Severity.WARNING
    assert "no longer matches what Coffer installs" in item.reason
    assert item.since is not None
    assert (item.action.verb, item.action.method, item.action.path) == (
        "repair",
        "POST",
        APPLY_PATH,
    )
    assert item.action.body == {"ids": [result.change.id]}
