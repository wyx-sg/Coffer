"""SkillService — import/fetch/update/enable/disable/verify/remove for skills.

Stitches together MasterStore (canonical files), SkillBindingRepo (per-agent
state), SourceFetcher (git), SyncEngine (per-OS link helper), and the
kind-agnostic ResourceService (Resource rows + audit).
"""

from __future__ import annotations

import contextlib
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.skill.ports import (
    MasterStorePort,
    SkillBindingRepoPort,
    SourceFetcherPort,
    SyncEnginePort,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    CofferError,
    ResourceAlreadyExists,
    SkillValidationError,
    TargetConflict,
    UpdateNotSupported,
)
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.skill.binding import BindingState, LinkMode
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.drift import DriftReport
from coffer.domain.skill.source import GitSource, LocalImportSource
from coffer.domain.skill.validator import (
    ValidationFailure,
    ValidationOk,
    validate_skill_folder,
)

# Type for the agent skill_dir resolver injected by the composition root.
# Takes a Resource (kind='agent') and returns its effective on-disk skill
# directory. Defined as a Callable so SkillService doesn't import agent-kind
# modules (Contract 5).
AgentSkillDirResolver = Callable[[Resource], pathlib.Path]


@dataclass(frozen=True)
class UpdateOutcome:
    skill: Resource
    changed: bool
    renamed_from: str | None = None


class SkillService:
    """Skill-kind lifecycle on top of the kind-agnostic Resource framework."""

    def __init__(
        self,
        *,
        resource_service: ResourceService,
        audit: AuditService,
        binding_repo: SkillBindingRepoPort,
        master_store: MasterStorePort,
        source_fetcher: SourceFetcherPort,
        sync_engine: SyncEnginePort,
        agent_skill_dir_resolver: AgentSkillDirResolver,
        size_limit_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self._rs = resource_service
        self._audit = audit
        self._bindings = binding_repo
        self._store = master_store
        self._fetcher = source_fetcher
        self._sync = sync_engine
        self._resolve_agent_skill_dir = agent_skill_dir_resolver
        self._size_limit = size_limit_bytes

    # ---------- imports ----------

    async def import_local(self, *, path: str, actor: str = "api") -> Resource:
        src = pathlib.Path(path).expanduser().resolve()
        result = validate_skill_folder(src, size_limit_bytes=self._size_limit)
        if isinstance(result, ValidationFailure):
            raise SkillValidationError(result.reason, result.details)
        return await self._register_from_validated(
            src=src,
            validation=result,
            source_meta=LocalImportSource(original_path=str(src)),
            event=AuditEventType.SKILL_IMPORTED,
            actor=actor,
        )

    async def fetch_git(
        self,
        *,
        git_url: str,
        git_ref: str,
        git_subpath: str = "",
        actor: str = "api",
    ) -> Resource:
        async with self._fetcher.fetched(
            git_url=git_url, git_ref=git_ref, git_subpath=git_subpath
        ) as folder:
            result = validate_skill_folder(folder, size_limit_bytes=self._size_limit)
            if isinstance(result, ValidationFailure):
                raise SkillValidationError(result.reason, result.details)
            return await self._register_from_validated(
                src=folder,
                validation=result,
                source_meta=GitSource(
                    git_url=git_url,  # type: ignore[arg-type]
                    git_ref=git_ref,
                    git_subpath=git_subpath,
                ),
                event=AuditEventType.SKILL_FETCHED,
                actor=actor,
            )

    async def _register_from_validated(
        self,
        *,
        src: pathlib.Path,
        validation: ValidationOk,
        source_meta: LocalImportSource | GitSource,
        event: AuditEventType,
        actor: str,
    ) -> Resource:
        name = validation.frontmatter.name
        # Duplicate check before copying any bytes.
        existing = await self._rs.list(kind="skill")
        if any(r.name == name for r in existing):
            raise ResourceAlreadyExists("skill", name)
        if self._store.exists(name):
            raise ResourceAlreadyExists("skill", name)

        now = datetime.now(tz=UTC)
        cfg = SkillConfig(
            source=source_meta,
            skill_md_name=name,
            skill_md_description=validation.frontmatter.description,
            version_hash=validation.skill_md_sha256,
            last_synced_from_source_at=now,
        )

        # Stage master folder
        self._store.copy_in(
            src=src,
            name=name,
            meta={
                "name": name,
                "source": source_meta.model_dump(mode="json"),
                "imported_at": now,
                "version_hash": validation.skill_md_sha256,
            },
        )
        try:
            r = await self._rs.register(
                kind="skill",
                name=name,
                config=cfg.model_dump(mode="json"),
                description=validation.frontmatter.description,
                actor=actor,
            )
        except Exception:
            # Best-effort rollback of master
            self._store.delete(name)
            raise

        await self._audit.record(
            event.value,
            ref=ResourceRef("skill", name),
            actor=actor,
            details={"version_hash": validation.skill_md_sha256},
        )

        # Auto-bind for every enabled agent (trust mode).
        await self._auto_bind_all(skill=r, actor=actor)
        return r

    async def _auto_bind_all(self, *, skill: Resource, actor: str) -> None:
        agents = await self._rs.list(kind="agent")
        for a in agents:
            if not a.enabled:
                continue
            try:
                await self.enable_for(
                    skill_name=skill.name,
                    agent_name=a.name,
                    force=False,
                    actor=actor,
                )
            except (CofferError, OSError):
                # Skip — any domain-level failure (TargetConflict, config
                # validation, …) or an OSError on a single agent must not
                # abort auto-bind for the rest. Caller can re-enable later.
                continue

    # ---------- updates ----------

    async def update(
        self,
        *,
        name: str,
        allow_rename: bool = False,
        actor: str = "api",
    ) -> UpdateOutcome:
        from coffer.application.skill.update_ops import apply_update

        existing = await self._rs.get(ResourceRef("skill", name))
        cfg = SkillConfig.model_validate(existing.config)
        if not isinstance(cfg.source, GitSource):
            raise UpdateNotSupported("local_import sources cannot be auto-updated; re-import")
        async with self._fetcher.fetched(
            git_url=str(cfg.source.git_url),
            git_ref=cfg.source.git_ref,
            git_subpath=cfg.source.git_subpath,
        ) as folder:
            result = validate_skill_folder(folder, size_limit_bytes=self._size_limit)
            if isinstance(result, ValidationFailure):
                raise SkillValidationError(result.reason, result.details)
            return await apply_update(
                service=self,
                existing=existing,
                cfg=cfg,
                validation=result,
                src=folder,
                allow_rename=allow_rename,
                actor=actor,
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
        skill = await self._rs.get(ResourceRef("skill", skill_name))
        agent = await self._rs.get(ResourceRef("agent", agent_name))
        target_dir = self._resolve_agent_skill_dir(agent)
        link_path = target_dir / skill_name
        master = self._store.paths_for(skill_name).folder

        # The mode recorded on any prior binding — needed so a copy-fallback
        # target (a real directory by design) isn't misread as drift.
        prior = await self._bindings.find(skill_id=skill.id, agent_id=agent.id)
        prior_mode = prior.link_mode if prior else None

        # Resolve target conflicts.
        if link_path.exists() or link_path.is_symlink():
            status = self._sync.classify_target(
                link=link_path, expected_master=master, link_mode=prior_mode
            )
            if status.drift is None:
                # Already linked correctly — idempotent. Preserve the real mode.
                return await self._bindings.upsert(
                    skill_id=skill.id,
                    agent_id=agent.id,
                    enabled=True,
                    last_linked_at=datetime.now(tz=UTC),
                    last_link_path=str(link_path),
                    link_mode=prior_mode or LinkMode.SYMLINK,
                )
            if not force:
                raise TargetConflict(str(link_path), status.drift.value)
            # Backup + remove. Microseconds in the suffix so two force=True
            # enables in the same second produce unique backup names.
            backup = link_path.with_name(
                f"{link_path.name}.coffer-backup-"
                f"{int(datetime.now(tz=UTC).timestamp() * 1_000_000)}"
            )
            link_path.rename(backup)

        # Ensure the agent's skill_dir parent is in place.
        target_dir.mkdir(parents=True, exist_ok=True)

        mode = self._sync.make_directory_link(target=master, link=link_path)
        binding = await self._bindings.upsert(
            skill_id=skill.id,
            agent_id=agent.id,
            enabled=True,
            last_linked_at=datetime.now(tz=UTC),
            last_link_path=str(link_path),
            link_mode=mode,
        )
        await self._audit.record(
            AuditEventType.SKILL_BOUND.value,
            ref=ResourceRef("skill", skill_name),
            actor=actor,
            details={
                "agent": agent_name,
                "link": str(link_path),
                "mode": mode.value,
            },
        )
        return binding

    async def disable_for(
        self, *, skill_name: str, agent_name: str, actor: str = "api"
    ) -> BindingState:
        skill = await self._rs.get(ResourceRef("skill", skill_name))
        agent = await self._rs.get(ResourceRef("agent", agent_name))
        existing = await self._bindings.find(skill_id=skill.id, agent_id=agent.id)
        if existing and existing.last_link_path:
            with contextlib.suppress(OSError):
                self._sync.remove_directory_link(pathlib.Path(existing.last_link_path))
        binding = await self._bindings.upsert(
            skill_id=skill.id,
            agent_id=agent.id,
            enabled=False,
            last_link_path=None,
            link_mode=None,
        )
        await self._audit.record(
            AuditEventType.SKILL_UNBOUND.value,
            ref=ResourceRef("skill", skill_name),
            actor=actor,
            details={"agent": agent_name},
        )
        return binding

    async def verify(self) -> DriftReport:
        from coffer.application.skill.verify_ops import verify_drift

        return await verify_drift(self)

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

    async def _cleanup_bindings_internal(self, *, skill_id: int) -> None:
        self._unlink_all(await self._bindings.list_for_skill(skill_id))
        await self._bindings.delete_for_skill(skill_id)

    def _unlink_all(self, bindings: list[BindingState]) -> None:
        """Best-effort symlink teardown for a list of bindings."""
        for b in bindings:
            if b.last_link_path:
                with contextlib.suppress(OSError):
                    self._sync.remove_directory_link(pathlib.Path(b.last_link_path))

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
