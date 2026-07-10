"""Memory scope resolution (cwd → git-root → project ULID → store).

Resolves a requested scope to a concrete :class:`ResolvedScope` and
**auto-provisions** the backing memory-store Resource if absent:

- ``global`` → one store keyed by ``WORKSPACE_GLOBAL_PROJECT_ID``, resource
  name ``"global"``.
- ``project`` → one store per project, keyed by a deterministic ULID derived
  from the cwd's git-root; resource name ``"project-<ulid>"``. If the cwd is not
  inside a git project, ``ScopeUnresolved`` is raised (``global`` still works).

Memory stores are Resources for lifecycle/audit, but the user never "creates"
one — first use provisions it.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceNotFound, ScopeUnresolved
from coffer.domain.knowledge.document import WORKSPACE_GLOBAL_PROJECT_ID
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.scope import MemoryScope, ResolvedScope
from coffer.domain.resource import ResourceRef

KIND_MEMORY = "memory"
GLOBAL_STORE_NAME = "global"

#: Injected helpers (so the resolver stays free of filesystem imports).
GitRootFn = Callable[[str], "Path | None"]
ProjectUlidFn = Callable[[str], str]
StoreDirFn = Callable[[str], "Path"]
#: Records ``store_name -> project_root`` at provisioning time (finding #10).
RecordRootFn = Callable[[str, str], Awaitable[None]]
#: One-time adoption of a legacy (path-derived) store under the portable id.
MigrateStoreFn = Callable[[str, str, str], Awaitable[None]]
#: FR-058: the surviving store name for a merged-away project identity (or None).
AliasTargetFn = Callable[[str], Awaitable["str | None"]]


def project_store_name(project_id: str) -> str:
    """The Resource name for a per-project store."""
    return f"project-{project_id}"


#: Valid store names: ``global`` or ``project-<26-char Crockford base32 id>``.
_PROJECT_STORE_NAME = re.compile(r"^project-[0-9A-HJKMNP-TV-Z]{26}$")


def is_valid_store_name(name: str) -> bool:
    """Whether ``name`` has a shape a memory store can legally carry.

    Surfaces validate with this before touching a store so an arbitrary path
    segment can neither manufacture a Resource nor reach the ``project-``
    prefix-stripping helpers with a mangled name."""
    return name == GLOBAL_STORE_NAME or bool(_PROJECT_STORE_NAME.match(name))


class ScopeResolver:
    """Resolves scopes to stores and lazily provisions the backing Resource."""

    def __init__(
        self,
        *,
        resources: ResourceService,
        git_root: GitRootFn,
        project_ulid: ProjectUlidFn,
        store_dir: StoreDirFn,
        record_project_root: RecordRootFn | None = None,
        legacy_project_ulid: ProjectUlidFn | None = None,
        migrate_store: MigrateStoreFn | None = None,
        merged_alias_target: AliasTargetFn | None = None,
    ) -> None:
        self._resources = resources
        self._git_root = git_root
        self._project_ulid = project_ulid
        self._store_dir = store_dir
        self._legacy_project_ulid = legacy_project_ulid
        self._migrate_store = migrate_store
        self._merged_alias_target = merged_alias_target
        # Optional persistence hook: when a project store is provisioned, record
        # its originating git-root so the surface can echo it back (finding #10).
        self._record_project_root = record_project_root

    async def resolve(self, *, scope: MemoryScope, cwd: str | None) -> ResolvedScope:
        """Resolve one scope, provisioning the store Resource if needed."""
        if scope is MemoryScope.GLOBAL:
            return await self._resolve_global()
        return await self._resolve_project(cwd)

    async def resolve_recall_scopes(self, *, cwd: str | None) -> list[ResolvedScope]:
        """Stores a default ``recall`` spans: project (if resolvable) + global."""
        scopes: list[ResolvedScope] = []
        if cwd is not None and self._git_root(cwd) is not None:
            scopes.append(await self._resolve_project(cwd))
        scopes.append(await self._resolve_global())
        return scopes

    # ----- internals -----

    async def _resolve_global(self) -> ResolvedScope:
        await self._ensure_store(GLOBAL_STORE_NAME)
        return ResolvedScope(
            scope=MemoryScope.GLOBAL,
            project_id=WORKSPACE_GLOBAL_PROJECT_ID,
            store_dir=self._store_dir(WORKSPACE_GLOBAL_PROJECT_ID),
        )

    async def _resolve_project(self, cwd: str | None) -> ResolvedScope:
        if cwd is None:
            raise ScopeUnresolved("<none>")
        root = self._git_root(cwd)
        if root is None:
            raise ScopeUnresolved(cwd)
        project_id = self._project_ulid(str(root))
        project_id = await self._maybe_redirect_merged(project_id)
        store_name = project_store_name(project_id)
        await self._maybe_migrate_legacy(str(root), project_id)
        await self._ensure_store(store_name)
        if self._record_project_root is not None:
            await self._record_project_root(store_name, str(root))
        return ResolvedScope(
            scope=MemoryScope.PROJECT,
            project_id=project_id,
            store_dir=self._store_dir(project_id),
        )

    async def _maybe_redirect_merged(self, project_id: str) -> str:
        """FR-058: a merged-away identity resolves to its surviving store.

        Consulted only on a MISS — when the computed identity's own store
        still exists the hot path is untouched. Returns the (possibly
        redirected) project id."""
        if self._merged_alias_target is None:
            return project_id
        try:
            await self._resources.get(ResourceRef(KIND_MEMORY, project_store_name(project_id)))
            return project_id  # the store exists — no redirect
        except ResourceNotFound:
            pass
        target = await self._merged_alias_target(project_id)
        if target is None or not is_valid_store_name(target) or target == GLOBAL_STORE_NAME:
            return project_id
        return target[len("project-") :]

    async def _maybe_migrate_legacy(self, root: str, project_id: str) -> None:
        """Adopt a surviving pre-portable-identity store: same repo, old
        path-derived id. The portable store already existing is NOT a reason
        to skip — on a second synced machine the portable store arrives via
        sync while that machine's own legacy store (different path, different
        id) still holds its facts; adoption merges them in additively
        (spec 007 FR-004a / ADR-043)."""
        if self._legacy_project_ulid is None or self._migrate_store is None:
            return
        legacy_id = self._legacy_project_ulid(root)
        if legacy_id == project_id:
            return
        try:
            await self._resources.get(ResourceRef(KIND_MEMORY, project_store_name(legacy_id)))
        except ResourceNotFound:
            return  # nothing to adopt
        await self._migrate_store(legacy_id, project_id, root)

    async def _ensure_store(self, store_name: str) -> None:
        ref = ResourceRef(kind=KIND_MEMORY, name=store_name)
        try:
            await self._resources.get(ref)
            return
        except ResourceNotFound:
            pass
        # Provision with defaults (keyword + grep, offline, no embedding).
        await self._resources.register(
            kind=KIND_MEMORY,
            name=store_name,
            config=MemoryStoreConfig().model_dump(mode="json"),
            actor="system",
            description=("Global agent memory" if store_name == GLOBAL_STORE_NAME else None),
        )
