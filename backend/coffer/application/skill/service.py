"""SkillService — import/enable/disable/verify/remove for skills.

Stitches together MasterStore (canonical files), SkillBindingRepo (per-agent
state), SyncEngine (per-OS link helper), and the kind-agnostic ResourceService
(Resource rows + audit).
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
import shutil
from collections.abc import Callable
from typing import TYPE_CHECKING

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.skill import delivery_ops
from coffer.application.skill.ports import (
    ExternalDirRegistrarPort,
    MasterStorePort,
    SkillBindingRepoPort,
    SyncEnginePort,
    WorkspaceScanPort,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SkillValidationError
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.skill.binding import BindingState
from coffer.domain.skill.drift import (
    DriftReport,
    RepairResult,
)
from coffer.domain.skill.external_dir import ExternalDirRegistration
from coffer.domain.skill.source import LocalImportSource
from coffer.domain.skill.validator import (
    ValidationFailure,
    validate_skill_folder,
)

if TYPE_CHECKING:
    from coffer.application.skill.unmanaged_ops import UnmanagedView

logger = logging.getLogger(__name__)

# Type for the agent skill_dir resolver injected by the composition root.
# Takes a Resource (kind='agent') and returns its effective on-disk skill
# directory. Defined as a Callable so SkillService doesn't import agent-kind
# modules (Contract 5).
AgentSkillDirResolver = Callable[[Resource], pathlib.Path]

# Resolver for an agent's ordered unmanaged-skill scan locations (FR-022).
# Built at the composition root from AgentConfig +
# coffer.domain.agent.scan.scan_locations — same Contract 5 seam as above.
AgentScanLocationsResolver = Callable[[Resource], list[pathlib.Path]]

# Resolver for an agent's follow policy (FR-025): returns
# ``(follow_all_skills, skill_exclusions)``. Built at the composition root
# from AgentConfig — same Contract 5 seam as above.
AgentSkillPolicyResolver = Callable[[Resource], tuple[bool, list[str]]]

# Resolver for an agent's skill-delivery MODE (spec 005): a plain ``str`` (the
# SkillDeliveryMode value, never the enum, so this layer imports no agent-kind
# code — Contract 5). Built at the composition root from the descriptor.
AgentSkillDeliveryResolver = Callable[[Resource], str]

# Resolver for an agent's external-dir registration (spec 005, EXTERNAL_DIR
# mode): an ``ExternalDirRegistration`` for EXTERNAL_DIR agents, ``None``
# otherwise.
AgentExternalRegistrationResolver = Callable[[Resource], ExternalDirRegistration | None]


class SkillService:
    """Skill-kind lifecycle on top of the kind-agnostic Resource framework."""

    def __init__(
        self,
        *,
        resource_service: ResourceService,
        audit: AuditService,
        binding_repo: SkillBindingRepoPort,
        master_store: MasterStorePort,
        sync_engine: SyncEnginePort,
        agent_skill_dir_resolver: AgentSkillDirResolver,
        size_limit_bytes: int = 50 * 1024 * 1024,
        workspace_scan: WorkspaceScanPort | None = None,
        agent_scan_locations_resolver: AgentScanLocationsResolver | None = None,
        agent_skill_policy_resolver: AgentSkillPolicyResolver | None = None,
        agent_skill_delivery_resolver: AgentSkillDeliveryResolver | None = None,
        external_dir_registrar: ExternalDirRegistrarPort | None = None,
        agent_external_registration_resolver: AgentExternalRegistrationResolver | None = None,
        rmtree: Callable[[pathlib.Path], None] = shutil.rmtree,
    ) -> None:
        self._rs = resource_service
        self._audit = audit
        self._bindings = binding_repo
        self._store = master_store
        self._sync = sync_engine
        self._resolve_agent_skill_dir = agent_skill_dir_resolver
        self._size_limit = size_limit_bytes
        # Unmanaged-skill discovery deps (FR-022). Optional only so existing
        # construction sites keep working until the composition root wires
        # them; the unmanaged_* methods guard against missing config.
        self._workspace_scan = workspace_scan
        self._resolve_agent_scan_locations = agent_scan_locations_resolver
        # Follow-policy resolver (FR-025). Optional: an unwired context falls
        # back to (True, []) — the pre-amendment trust-mode auto-bind.
        self._agent_skill_policy_resolver = agent_skill_policy_resolver
        # Skill-delivery-mode resolver (spec 005); unwired → folder model.
        self._agent_skill_delivery_resolver = agent_skill_delivery_resolver
        # EXTERNAL_DIR delivery (spec 005): registrar edits the agent's config,
        # resolver yields where/how; unwired → skip registration.
        self._external_dir_registrar = external_dir_registrar
        self._agent_external_registration_resolver = agent_external_registration_resolver
        self._rmtree = rmtree

    # ---------- imports ----------

    async def import_local(
        self, *, path: str, actor: str = "api", overwrite: bool = False
    ) -> Resource:
        from coffer.application.skill.lifecycle_ops import register_from_validated

        src = pathlib.Path(path).expanduser().resolve()
        result = validate_skill_folder(src, size_limit_bytes=self._size_limit)
        if isinstance(result, ValidationFailure):
            raise SkillValidationError(result.reason, result.details)
        return await register_from_validated(
            service=self,
            src=src,
            validation=result,
            source_meta=LocalImportSource(original_path=str(src)),
            event=AuditEventType.SKILL_IMPORTED,
            actor=actor,
            overwrite=overwrite,
        )

    # ---------- per-agent bindings ----------

    async def enable_for(
        self,
        *,
        skill_name: str,
        agent_name: str,
        force: bool = False,
        actor: str = "api",
    ) -> BindingState:
        """Deliver a skill to an agent (link + binding row). Delegates to
        ``binding_ops`` to keep this module under the size limit."""
        from coffer.application.skill.binding_ops import enable_skill_for_agent

        return await enable_skill_for_agent(
            service=self, skill_name=skill_name, agent_name=agent_name, force=force, actor=actor
        )

    async def disable_for(
        self, *, skill_name: str, agent_name: str, actor: str = "api"
    ) -> BindingState:
        """Remove a skill's link for an agent and disable the binding row."""
        from coffer.application.skill.binding_ops import disable_skill_for_agent

        return await disable_skill_for_agent(
            service=self, skill_name=skill_name, agent_name=agent_name, actor=actor
        )

    # ---------- follow-master-library (FR-025) ----------

    def _resolve_agent_skill_policy(self, agent: Resource) -> tuple[bool, list[str]]:
        """(follow_all_skills, skill_exclusions) for an agent resource.

        Unwired contexts default to ``(True, [])`` — the pre-amendment
        trust-mode auto-bind behavior.
        """
        if self._agent_skill_policy_resolver is None:
            return (True, [])
        return self._agent_skill_policy_resolver(agent)

    async def apply_follow_for_agent(self, agent_name: str, *, actor: str = "system") -> None:
        """Reconcile an agent's deliveries with its follow policy.

        Wired as the agent kind's on-skill-policy-changed hook (and invoked
        after registration). See ``follow_ops`` for semantics.
        """
        from coffer.application.skill.follow_ops import apply_follow_for_agent

        await apply_follow_for_agent(service=self, agent_name=agent_name, actor=actor)

    async def verify(self) -> DriftReport:
        from coffer.application.skill.verify_ops import verify_drift

        return await verify_drift(self)

    async def repair_drift(self, *, actor: str = "api") -> RepairResult:
        """Opt-in drift repair: re-deliver safely-repairable drift kinds.

        Delegates to ``verify_ops.repair_drift`` to keep this module under the
        file-size limit.  See that function for full semantics.
        """
        from coffer.application.skill.verify_ops import repair_drift

        return await repair_drift(self, actor=actor)

    async def remove(self, *, name: str, actor: str = "api") -> None:
        # All on-disk teardown happens inside the awaited on_delete hook,
        # so this path and the kind-agnostic DELETE share one cleanup flow.
        await self._rs.delete(ResourceRef("skill", name), actor=actor)

    async def cleanup_bindings_for_skill(self, ref: ResourceRef) -> None:
        """on_delete hook: tear down symlinks + binding rows + master folder.

        Awaited by ResourceService BEFORE the row is removed, so the
        kind-agnostic delete leaves no on-disk orphans. ``store.delete`` is
        idempotent so re-entry (e.g. from a test that pre-cleans) is safe.
        """
        skill = await self._rs.get(ref)
        await self._cleanup_bindings_internal(skill_id=skill.id)
        self._store.delete(ref.name)

    async def cleanup_bindings_for_agent(self, ref: ResourceRef) -> None:
        """Hook bound to `agent` Kind's `on_delete` at the composition root."""
        agent = await self._rs.get(ref)
        self._unlink_all(await self._bindings.list_for_agent(agent.id))
        await self._bindings.delete_for_agent(agent.id)
        # Agent + bindings gone — drop any external-dir registration in its config.
        delivery_ops.deregister_external(self, agent)

    async def _cleanup_bindings_internal(self, *, skill_id: int) -> None:
        bindings = await self._bindings.list_for_skill(skill_id)
        affected_agent_ids = {b.agent_resource_id for b in bindings}
        self._unlink_all(bindings)
        await self._bindings.delete_for_skill(skill_id)
        # A removed skill may have been an external-dir agent's last one —
        # reconcile each affected agent's registration.
        for agent_id in affected_agent_ids:
            agent = await self._get_agent_by_id(agent_id)
            if agent is not None:
                await delivery_ops.reconcile_external_registration(self, agent)

    def _unlink_all(self, bindings: list[BindingState]) -> None:
        """Best-effort symlink teardown for a list of bindings."""
        for b in bindings:
            if b.last_link_path:
                with contextlib.suppress(OSError):
                    self._sync.remove_directory_link(
                        pathlib.Path(b.last_link_path), link_mode=b.link_mode
                    )

    async def relink_for_agent(self, agent_name: str, *, actor: str = "api") -> None:
        """Re-deliver an agent's skills after its config_dir changed.

        Wired as the agent kind's on-config-dir-changed hook (see
        ``agent_skill_wiring``). Delegates to ``lifecycle_ops`` to keep this
        module under the size limit.
        """
        from coffer.application.skill.lifecycle_ops import relink_agent_skills

        await relink_agent_skills(service=self, agent_name=agent_name, actor=actor)

    # ---------- unmanaged skills (FR-022) ----------

    def _require_unmanaged_deps(self) -> None:
        if self._workspace_scan is None or self._resolve_agent_scan_locations is None:
            raise RuntimeError(
                "SkillService was constructed without workspace_scan / "
                "agent_scan_locations_resolver — the composition root must "
                "provide both for unmanaged-skill operations"
            )

    async def list_unmanaged(self, agent_name: str) -> list[UnmanagedView]:
        from coffer.application.skill.unmanaged_ops import list_unmanaged

        self._require_unmanaged_deps()
        return await list_unmanaged(service=self, agent_name=agent_name)

    async def adopt_unmanaged(
        self, *, agent_name: str, skill_name: str, location: str, actor: str = "api"
    ) -> Resource:
        from coffer.application.skill.unmanaged_ops import adopt_unmanaged

        self._require_unmanaged_deps()
        return await adopt_unmanaged(
            service=self,
            agent_name=agent_name,
            skill_name=skill_name,
            location=location,
            actor=actor,
        )

    async def delete_unmanaged(
        self, *, agent_name: str, skill_name: str, location: str, actor: str = "api"
    ) -> None:
        from coffer.application.skill.unmanaged_ops import delete_unmanaged

        self._require_unmanaged_deps()
        await delete_unmanaged(
            service=self,
            agent_name=agent_name,
            skill_name=skill_name,
            location=location,
            actor=actor,
        )

    # ---------- helpers ----------

    async def _get_agent_by_id(self, agent_id: int) -> Resource | None:
        # ResourceService doesn't expose by-id lookup; use list-then-filter.
        for a in await self._rs.list(kind="agent"):
            if a.id == agent_id:
                return a
        return None

    async def bindings_for(self, skill_name: str) -> list[BindingState]:
        skill = await self._rs.get(ResourceRef("skill", skill_name))
        return await self._bindings.list_for_skill(skill.id)

    async def bindings_grouped_by_skill(self) -> dict[int, list[BindingState]]:
        """``skill_resource_id -> [bindings]`` map; collapses N+1 in list."""
        grouped: dict[int, list[BindingState]] = {}
        for b in await self._bindings.list_all():
            grouped.setdefault(b.skill_resource_id, []).append(b)
        return grouped

    # ---------- read API for surfaces ----------

    async def list_skills(self) -> list[Resource]:
        return await self._rs.list(kind="skill")

    async def get_skill(self, name: str) -> Resource:
        return await self._rs.get(ResourceRef("skill", name))

    def master_path(self, name: str) -> str:
        """On-disk path of a skill's canonical master folder (for surfaces)."""
        return str(self._store.paths_for(name).folder)

    async def list_agents(self) -> list[Resource]:
        """Read-through to ResourceService so surfaces don't import it directly."""
        return await self._rs.list(kind="agent")
