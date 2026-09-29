"""The skill + agent service graph, wired the way the composition root wires it.

Real SQLite, a real ``MasterStore`` / ``SyncEngine`` under ``tmp_path``, and one
``Reconciler`` with the ``skill_link`` target registered: every front door
(import, a skill's ``enabled`` / ``scope``, an agent registered, switched or
moved) asks it for a pass, exactly as ``surfaces/http/agent_skill_wiring``
does. ``hooks=False`` leaves the kind hooks out, so a test can change a row
without a pass and then drive one by hand.
"""

from __future__ import annotations

import pathlib
import textwrap
from dataclasses import dataclass
from typing import Any

from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.application.skill.kind import make_skill_kind
from coffer.application.skill.link_reconcile import TARGET, SkillLinkTarget
from coffer.application.skill.service import SkillService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.scan import scan_locations
from coffer.domain.agent.types import AgentType
from coffer.domain.reconcile import PassReport, Trigger
from coffer.domain.resource import Resource
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.infrastructure.platform import HostPlatform
from coffer.infrastructure.skill.master_store import MasterStore
from coffer.infrastructure.skill.persistence import SkillBindingRepo
from coffer.infrastructure.skill.sync_engine import SyncEngine
from coffer.infrastructure.skill.workspace_scan import WorkspaceScan


@dataclass
class SkillGraph:
    engine: Any
    rs: ResourceService
    audit: AuditService
    skills: SkillService
    agents: AgentService
    store: MasterStore
    reconciler: Reconciler
    target: SkillLinkTarget

    async def run(self, trigger: Trigger = Trigger.BOOT) -> PassReport:
        """One writing ``skill_link`` pass."""
        return await self.reconciler.run(targets=[TARGET], trigger=trigger)

    async def plan(self) -> PassReport:
        return await self.reconciler.plan(targets=[TARGET])

    async def register_agent(
        self,
        tmp_path: pathlib.Path,
        *,
        name: str,
        agent_type: AgentType = AgentType.CLAUDE_CODE,
    ) -> tuple[Resource, pathlib.Path]:
        """Register an agent over ``<tmp_path>/<name>-cfg``; returns it and its
        skills directory."""
        config_dir = tmp_path / f"{name}-cfg"
        config_dir.mkdir()
        agent = await self.agents.register(
            agent_type=agent_type, name=name, config_dir=str(config_dir), actor="cli"
        )
        return agent, config_dir / "skills"

    async def import_skill(
        self, tmp_path: pathlib.Path, name: str, body: str = "hello"
    ) -> Resource:
        src = write_skill_folder(tmp_path / "srcs" / name, name=name, body=body)
        return await self.skills.import_local(path=str(src), actor="cli")

    async def delivered(self, agent: Resource) -> set[str]:
        """The names of the skills a binding row says ``agent`` holds."""
        names = {s.id: s.name for s in await self.skills.list_skills()}
        return {
            names[b.skill_resource_id]
            for b in await self.skills._bindings.list_for_agent(agent.id)
            if b.enabled and b.skill_resource_id in names
        }

    async def dispose(self) -> None:
        await self.engine.dispose()


def write_skill_folder(folder: pathlib.Path, *, name: str, body: str = "hello") -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: A test skill named {name}.
            ---

            {body}
            """
        ),
        encoding="utf-8",
    )
    return folder


async def build_skill_graph(
    tmp_path: pathlib.Path, *, hooks: bool = True, scan_home: pathlib.Path | None = None
) -> SkillGraph:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    store = MasterStore(root=tmp_path / "coffer-skills")
    reconciler = Reconciler(audit=audit)

    def _skill_dir(r: Resource) -> pathlib.Path:
        return AgentConfig.model_validate(r.config).resolved_skill_dir()

    def _scan_locations(r: Resource) -> list[pathlib.Path]:
        cfg = AgentConfig.model_validate(r.config)
        if scan_home is None:
            return scan_locations(cfg.type, cfg.resolved_config_dir())
        return scan_locations(cfg.type, cfg.resolved_config_dir(), home=scan_home)

    async def _deliver() -> PassReport:
        return await reconciler.run(targets=[TARGET], trigger=Trigger.CHANGE)

    kinds: dict[str, Any] = {}
    rs = ResourceService(kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    skills = SkillService(
        resource_service=rs,
        audit=audit,
        binding_repo=SkillBindingRepo(sm),
        master_store=store,
        sync_engine=SyncEngine(),
        agent_skill_dir_resolver=_skill_dir,
        workspace_scan=WorkspaceScan(),
        agent_scan_locations_resolver=_scan_locations,
        reconcile_delivery=_deliver,
    )
    target = SkillLinkTarget(service=skills)
    reconciler.register(target)

    async def _agent_changed(_uid: str) -> None:
        await _deliver()

    async def _changed(_r: Resource) -> None:
        await _deliver()

    agents = AgentService(
        platform=HostPlatform(),
        resource_service=rs,
        audit=audit,
        on_config_dir_changed=_agent_changed if hooks else None,
        reconcile_skill_delivery=_agent_changed if hooks else None,
    )
    kinds["agent"] = make_agent_kind(
        on_delete=skills.cleanup_bindings_for_agent,
        on_enabled_changed=_changed if hooks else None,
    )
    kinds["skill"] = make_skill_kind(
        skills.cleanup_bindings_for_skill,
        on_scope_changed=_changed if hooks else None,
        on_enabled_changed=_changed if hooks else None,
    )
    return SkillGraph(engine, rs, audit, skills, agents, store, reconciler, target)


__all__ = ["SkillGraph", "build_skill_graph", "write_skill_folder"]
