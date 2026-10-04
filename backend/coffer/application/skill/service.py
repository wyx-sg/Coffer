"""SkillService — import / remove / files / unmanaged skills for the skill kind.

Stitches together MasterStore (canonical files), SkillBindingRepo (per-agent
state), SyncEngine (per-OS link helper), and the kind-agnostic ResourceService
(Resource rows + audit).

Every operation here names a resource by its **uid**
(ADR identity-is-the-uid-inside-the-file). There is deliberately no by-name
entry point: a label a human typed is resolved once, at the surface they typed
it at (``ResourceService.get_by_name``), and what reaches this service is
already an identity. Names still appear as DATA further in — the master folder
and each delivered copy are directories named after the skill — but never as
the way one part of Coffer tells another which resource it means.
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
import shutil
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.skill.ports import (
    MasterStorePort,
    SkillBindingRepoPort,
    SyncEnginePort,
    WorkspaceScanPort,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SkillValidationError
from coffer.domain.reconcile import PassReport
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from coffer.domain.skill.binding import BindingState
from coffer.domain.skill.source import LocalImportSource
from coffer.domain.skill.validator import (
    ValidationFailure,
    validate_skill_folder,
)

if TYPE_CHECKING:
    from coffer.application.skill.copy_ops import KeptCopy
    from coffer.application.skill.delivery_report import AgentDelivery
    from coffer.application.skill.unmanaged_ops import UnmanagedDetail, UnmanagedView

logger = logging.getLogger(__name__)

# Type for the agent skill_dir resolver injected by the composition root.
# Takes a Resource (kind='agent') and returns its effective on-disk skill
# directory. Defined as a Callable so SkillService doesn't import agent-kind
# modules (Contract 5).
AgentSkillDirResolver = Callable[[Resource], pathlib.Path]

# Resolver for an agent's ordered unmanaged-skill scan locations (see "List unmanaged
# skills in an agent's skill locations"). Built at the composition root from AgentConfig
# + coffer.domain.agent.scan.scan_locations — same Contract 5 seam as above.
AgentScanLocationsResolver = Callable[[Resource], list[pathlib.Path]]

#: One ``skill_link`` reconcile pass, as the composition root hands it in.
DeliveryPass = Callable[[], Awaitable[PassReport]]


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
        workspace_scan: WorkspaceScanPort,
        agent_scan_locations_resolver: AgentScanLocationsResolver,
        size_limit_bytes: int = 50 * 1024 * 1024,
        rmtree: Callable[[pathlib.Path], None] = shutil.rmtree,
        reconcile_delivery: DeliveryPass | None = None,
    ) -> None:
        self._rs = resource_service
        self._audit = audit
        self._bindings = binding_repo
        self._store = master_store
        self._sync = sync_engine
        self._resolve_agent_skill_dir = agent_skill_dir_resolver
        self._size_limit = size_limit_bytes
        # Unmanaged-skill discovery deps (see "List unmanaged skills in an agent's skill
        # locations").
        self._workspace_scan = workspace_scan
        self._resolve_agent_scan_locations = agent_scan_locations_resolver
        self._rmtree = rmtree
        # Closes over the reconciler at the composition root, so this service
        # never imports a surface (see ``reconcile_delivery``).
        self._reconcile_delivery = reconcile_delivery
        #: Deletes in flight that keep an agent's own folder, by skill uid;
        #: the on_delete hook fills in the folders it left.
        self._keeping: dict[str, list[KeptCopy]] = {}
        #: The newest delivery pass a front door of this service asked for.
        self.last_delivery: PassReport | None = None

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

    # ---------- delivery ----------

    async def reconcile_delivery(self) -> PassReport | None:
        """Ask the reconciler for a ``skill_link`` pass now (``Trigger.CHANGE``).

        Every front door that changes what an agent should hold — an import,
        a skill's ``enabled`` / ``scope``, an agent registered or
        moved, the builtin seed — calls this after its own write, so the
        delivery is in place when the call returns. Delivery itself is the
        ``skill_link`` target's (``link_reconcile``); ``None`` when no
        reconciler is wired (a service built for one isolated test).
        """
        if self._reconcile_delivery is None:
            return None
        self.last_delivery = await self._reconcile_delivery()
        return self.last_delivery

    async def delivery_of(self, skill: Resource) -> list[AgentDelivery]:
        """Per agent, what the newest delivery pass did for ``skill``."""
        from coffer.application.skill.delivery_report import delivery_for

        return delivery_for(skill, await self.list_agents(), self.last_delivery)

    async def remove(
        self, *, uid: str, actor: str = "api", keep_foreign_copies: bool = False
    ) -> list[KeptCopy]:
        """Delete a skill. An agent's copy that is not Coffer's link refuses it
        (``SkillCopyNotOurs``); with ``keep_foreign_copies`` the delete goes ahead
        and the folders left alone are returned."""
        # All on-disk teardown happens inside the awaited on_delete hook,
        # so this path and the kind-agnostic DELETE share one cleanup flow.
        if not keep_foreign_copies:
            await self._rs.delete(uid, actor=actor)
            return []
        kept: list[KeptCopy] = []
        self._keeping[uid] = kept
        try:
            await self._rs.delete(uid, actor=actor)
        finally:
            self._keeping.pop(uid, None)
        return kept

    async def cleanup_bindings_for_skill(self, skill: Resource) -> None:
        """on_delete hook: tear down symlinks + binding rows + master folder.

        Awaited by ResourceService BEFORE the row is removed, so the
        kind-agnostic delete leaves no on-disk orphans. ``store.delete`` is
        idempotent so re-entry (e.g. from a test that pre-cleans) is safe.

        An agent's copy that is no longer Coffer's link stops the whole delete
        before anything is torn down (spec skill-manager "Refuse deleting a
        skill whose copy Coffer did not make").
        """
        from coffer.application.skill.copy_ops import refuse_foreign_copies

        keep = self._keeping.get(skill.uid)
        await refuse_foreign_copies(self, skill, keep=keep)
        await self._cleanup_bindings_internal(
            skill_uid=skill.uid, keep_paths=frozenset(k.path for k in keep or ())
        )
        self._store.delete(skill.name)

    async def cleanup_bindings_for_agent(self, agent: Resource) -> None:
        """Hook bound to `agent` Kind's `on_delete` at the composition root."""
        self._unlink_all(await self._bindings.list_for_agent(agent.uid))
        await self._bindings.delete_for_agent(agent.uid)

    async def _cleanup_bindings_internal(
        self, *, skill_uid: str, keep_paths: frozenset[str] = frozenset()
    ) -> None:
        bindings = await self._bindings.list_for_skill(skill_uid)
        self._unlink_all([b for b in bindings if b.last_link_path not in keep_paths])
        await self._bindings.delete_for_skill(skill_uid)

    def _unlink_all(self, bindings: list[BindingState]) -> None:
        """Best-effort symlink teardown for a list of bindings."""
        for b in bindings:
            if b.last_link_path:
                with contextlib.suppress(OSError):
                    self._sync.remove_directory_link(
                        pathlib.Path(b.last_link_path), link_mode=b.link_mode
                    )

    # ---------- unmanaged skills ----------

    # ``skill_name`` below is an on-disk DIRECTORY name, not a label Coffer
    # issued: an unmanaged skill has no resource row and so no uid to address
    # it by. The agent, which does have a row, is named by uid like everywhere
    # else.
    async def list_unmanaged(self, agent_uid: str) -> list[UnmanagedView]:
        from coffer.application.skill.unmanaged_ops import list_unmanaged

        return await list_unmanaged(service=self, agent_uid=agent_uid)

    async def get_unmanaged(
        self, *, agent_uid: str, skill_name: str, location: str
    ) -> UnmanagedDetail:
        from coffer.application.skill.unmanaged_ops import get_unmanaged

        return await get_unmanaged(
            service=self, agent_uid=agent_uid, skill_name=skill_name, location=location
        )

    async def adopt_unmanaged(
        self,
        *,
        agent_uid: str,
        skill_name: str,
        location: str,
        actor: str = "api",
        name: str | None = None,
        enabled: bool = True,
        scope: Scope | None = None,
    ) -> Resource:
        from coffer.application.skill.unmanaged_ops import adopt_unmanaged

        return await adopt_unmanaged(
            service=self,
            agent_uid=agent_uid,
            skill_name=skill_name,
            location=location,
            actor=actor,
            name=name,
            enabled=enabled,
            scope=scope,
        )

    async def delete_unmanaged(
        self, *, agent_uid: str, skill_name: str, location: str, actor: str = "api"
    ) -> None:
        from coffer.application.skill.unmanaged_ops import delete_unmanaged

        await delete_unmanaged(
            service=self,
            agent_uid=agent_uid,
            skill_name=skill_name,
            location=location,
            actor=actor,
        )

    # ---------- helpers ----------

    async def bindings_for(self, skill_uid: str) -> list[BindingState]:
        skill = await self._rs.get(skill_uid)
        return await self._bindings.list_for_skill(skill.uid)

    async def bindings_grouped_by_skill(self) -> dict[str, list[BindingState]]:
        """``skill_uid -> [bindings]`` map; collapses N+1 in list."""
        grouped: dict[str, list[BindingState]] = {}
        for b in await self._bindings.list_all():
            grouped.setdefault(b.skill_uid, []).append(b)
        return grouped

    # ---------- read API for surfaces ----------

    async def list_skills(self) -> list[Resource]:
        return await self._rs.list(kind="skill")

    async def get_skill(self, uid: str) -> Resource:
        return await self._rs.get(uid)

    def master_path(self, name: str) -> str:
        """On-disk path of a skill's canonical master folder (for surfaces)."""
        return str(self._store.paths_for(name).folder)

    async def list_agents(self) -> list[Resource]:
        """Read-through to ResourceService so surfaces don't import it directly."""
        return await self._rs.list(kind="agent")
