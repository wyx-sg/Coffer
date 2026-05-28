"""Composition-root helper that wires the agent + skill kinds into the app.

Extracted from `app.py` to keep that file under the size limit. The
cross-kind on_delete hook (deleting an agent cascades into skill binding
cleanup) is bound here because this module is allowed to import both kind
subpackages — they cannot import each other (Contract 5).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.skill.kind import make_skill_kind
from coffer.application.skill.service import SkillService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.agent.persistence import SuppressedAgentTypeRepo
from coffer.infrastructure.skill.master_store import MasterStore
from coffer.infrastructure.skill.persistence import SkillBindingRepo
from coffer.infrastructure.skill.source_fetcher import GitSourceFetcher
from coffer.infrastructure.skill.sync_engine import SyncEngine
from coffer.surfaces.http.dependencies import (
    set_agent_service,
    set_auto_detect_service,
    set_skill_service,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

_logger = logging.getLogger(__name__)


def wire_agent_and_skill_kinds(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
) -> None:
    """Wire the agent + skill kinds (specs 004, 005) into a running app.

    Mirrors the `wire_mcp_kind` pattern. Both kinds are wired in lockstep
    so the cross-kind on_delete hook can reference both services.
    """
    suppression_repo = SuppressedAgentTypeRepo(sm)  # type: ignore[arg-type]
    binding_repo = SkillBindingRepo(sm)  # type: ignore[arg-type]
    master_store = MasterStore()
    master_store.ensure_root()
    fetcher = GitSourceFetcher()
    sync_engine = SyncEngine()

    # Cross-kind resolver: skill service needs an agent's effective skill_dir
    # but cannot import agent-kind code itself (Contract 5).
    def _agent_skill_dir(r: Resource):  # type: ignore[no-untyped-def]
        return AgentConfig.model_validate(r.config).resolved_skill_dir()

    skill_svc = SkillService(
        resource_service=resource_svc,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        source_fetcher=fetcher,
        sync_engine=sync_engine,
        agent_skill_dir_resolver=_agent_skill_dir,
    )

    agent_svc = AgentService(
        resource_service=resource_svc,
        audit=audit,
        suppression_repo=suppression_repo,
    )
    detect_svc = AutoDetectService(
        agent_service=agent_svc,
        audit=audit,
        suppression_repo=suppression_repo,
    )

    async def _agent_on_delete(ref: ResourceRef) -> None:
        # Awaited by ResourceService.delete BEFORE the agent row is removed,
        # so binding-row lookups inside ``cleanup_bindings_for_agent`` still
        # resolve and every per-agent symlink is torn down. A previous
        # fire-and-forget implementation raced the row delete and left the
        # cleanup with nothing to find (silently dropped).
        await skill_svc.cleanup_bindings_for_agent(ref)

    agent_kind = make_agent_kind(on_delete=_agent_on_delete)
    skill_kind = make_skill_kind(skill_svc.cleanup_bindings_for_skill)

    app.state.kinds["agent"] = agent_kind
    app.state.kinds["skill"] = skill_kind

    set_agent_service(agent_svc)
    set_auto_detect_service(detect_svc)
    set_skill_service(skill_svc)

    # Best-effort first-run auto-detect — failures must not block startup.
    async def _initial_detect() -> None:
        try:
            await detect_svc.run_once(actor="system")
        except Exception:
            _logger.exception("agent.auto_detect.failed")

    loop = asyncio.get_running_loop()
    loop.create_task(_initial_detect())  # noqa: RUF006
