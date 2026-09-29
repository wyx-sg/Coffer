"""The delivery-hook reconcile target on real files, a real database and a
real ``Reconciler`` (ADR one-level-triggered-reconciler-compares-parameters).

Every test runs under an isolated HOME: the agents' config trees are laid out
by ``fake_agent_dir`` from their own descriptors, the database sits at the
home's ``~/.coffer/coffer.db``, and "connected" is the real answer — the agent
carries Coffer's gateway MCP entry, installed by ``AgentMcpService``.

- PR #413 reproduced: a hook carrying the dropped ``--agent`` option is found
  as a MODIFY of ``command`` and rewritten, foreign hooks untouched, one audit
  row from ``system`` (spec memory "Repair stale delivery hooks").
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
from coffer.application.audit_service import AuditService
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.delivery_reconcile import TARGET, DeliveryHookTarget
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.delivery import MARKER
from coffer.domain.reconcile import Disposition, Op, Outcome, Trigger
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.infrastructure.platform import HostPlatform
from tests.support.facets import agent_catalog
from tests.support.homes import FakeAgentDir, IsolatedHome, fake_agent_dir

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
        repo=SqlAlchemyResourceRepo(sm),
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


def _old_command(new: str, uid: str) -> str:
    """The command an older build installed: the same entry, passing the
    ``--agent`` option ``coffer memory context`` no longer takes."""
    stale = new.replace(f"--agent-uid {uid}", f"--agent {uid}")
    assert stale != new
    return stale


async def _connected_agent_with_stale_hook(
    rig: _Rig, agent_type: AgentType, name: str
) -> tuple[Resource, FakeAgentDir, pathlib.Path]:
    """An agent connected to Coffer whose settings file carries Coffer's hook
    with the OLD command, beside foreign hooks on the same and other events."""
    agent_dir = fake_agent_dir(rig.home, agent_type)
    agent = await rig.agents.register(agent_type=agent_type, name=name, actor="cli")
    await rig.mcp.install(agent.uid, actor="ui")
    adapter = agent_catalog().delivery_hook(agent_type)
    assert adapter is not None
    key = "settings" if agent_type is AgentType.CLAUDE_CODE else "hooks"
    if agent_type is AgentType.CLAUDE_CODE:
        stale = f': {MARKER}; coffer memory context --agent {agent.uid} --cwd "$PWD"'
    else:
        stale = _old_command(adapter.command_for(agent.uid), agent.uid)
    leaf = {"type": "command", "command": stale}
    doc = {
        "theme": "dark",
        "hooks": {
            adapter.event: [_FOREIGN_SESSION, {"hooks": [leaf]}],
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
@pytest.mark.parametrize(
    ("agent_type", "name"), [(AgentType.CLAUDE_CODE, "cc"), (AgentType.CODEX, "cx")]
)
async def test_pr_413_a_hook_passing_a_dropped_option_is_repaired(
    rig: _Rig, agent_type: AgentType, name: str
) -> None:
    agent, _dir, path = await _connected_agent_with_stale_hook(rig, agent_type, name)
    adapter = agent_catalog().delivery_hook(agent_type)
    assert adapter is not None

    plan = await rig.reconciler.plan(targets=[TARGET], trigger=Trigger.PERIOD)
    (planned,) = plan.results
    assert planned.change.difference.op is Op.MODIFY
    assert planned.change.difference.changed_params == ("command",)
    assert planned.change.decision.disposition is Disposition.REPAIR
    assert planned.change.decision.reason_code == "stale_command"

    report = await rig.reconciler.run(trigger=Trigger.PERIOD)

    (result,) = report.results
    assert result.outcome is Outcome.APPLIED
    data = json.loads(path.read_text())
    assert data["theme"] == "dark"
    assert data["hooks"]["Stop"] == [_FOREIGN_STOP]
    groups = data["hooks"][adapter.event]
    assert _FOREIGN_SESSION in groups
    coffer_commands = [
        leaf["command"] for g in groups for leaf in g["hooks"] if MARKER in leaf["command"]
    ]
    assert coffer_commands == [adapter.command_for(agent.uid)]
    assert path.with_name(path.name + ".bak").exists()

    rows = await rig.audit.query(
        resource=agent, event_type=AuditEventType.MEMORY_DELIVERY_INSTALLED.value
    )
    assert len(rows) == 1
    assert rows[0].actor == "system"
    assert rows[0].details["path"] == str(path)
    assert rows[0].details["reason"] == "stale_command"

    # Converged: the next pass finds nothing to do.
    assert (await rig.reconciler.run(trigger=Trigger.PERIOD)).results == ()


async def test_an_audit_that_cannot_be_recorded_puts_the_file_back(
    rig: _Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    _agent, _dir, path = await _connected_agent_with_stale_hook(rig, AgentType.CLAUDE_CODE, "cc")
    before = path.read_text()

    async def _refuse(entry: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(rig.repo, "insert", _refuse)
    report = await rig.reconciler.run(trigger=Trigger.PERIOD)

    (result,) = report.results
    assert result.outcome is Outcome.FAILED
    assert "audit not recorded" in (result.error or "")
    assert path.read_text() == before


def _fingerprint(root: pathlib.Path) -> dict[str, tuple[int, str, int]]:
    out: dict[str, tuple[int, str, int]] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            st = p.stat()
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            out[str(p.relative_to(root))] = (st.st_size, digest, st.st_mtime_ns)
    return out


async def test_a_dry_run_writes_nothing_under_home(rig: _Rig) -> None:
    await _connected_agent_with_stale_hook(rig, AgentType.CLAUDE_CODE, "cc")
    await _connected_agent_with_stale_hook(rig, AgentType.CODEX, "cx")
    assert rig.home.db_path.is_file()
    files_before = _fingerprint(rig.home.root)
    rows_before = await rig.audit_count()

    plan = await rig.reconciler.plan()

    assert _fingerprint(rig.home.root) == files_before
    assert await rig.audit_count() == rows_before
    assert plan.dry_run is True
    assert [r.change.difference.op for r in plan.results] == [Op.MODIFY, Op.MODIFY]
    assert all(r.outcome is Outcome.PLANNED for r in plan.results)
    assert rig.reconciler.pending_hints == {}
    assert rig.reconciler.last_pass is None
