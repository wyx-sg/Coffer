"""Knowledge scope resolution (cwd → git-root → project ULID → scope dir).

Resolves a requested scope to a concrete :class:`ResolvedScope`. Two of the
three scopes **auto-provision** their backing Resource:

- ``global`` → one scope keyed by ``WORKSPACE_GLOBAL_PROJECT_ID``, resource
  name ``"global"``.
- ``project`` → one scope per project, keyed by a deterministic ULID derived
  from the cwd's git-root; resource name ``"project-<ulid>"``. If the cwd is not
  inside a git project, ``ScopeUnresolved`` is raised (``global`` still works).
- a **named collection** → resolved by name and **never provisioned**. The
  first two exist because an agent wanted to write something; a named
  collection exists because someone decided it should, so a typo must be an
  error rather than a new empty collection.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from pathlib import Path

from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceNotFound, ScopeUnresolved
from coffer.domain.knowledge.document import KIND_KNOWLEDGE, WORKSPACE_GLOBAL_PROJECT_ID
from coffer.domain.knowledge.scope import (
    GLOBAL_SCOPE_NAME,
    PROJECT_SCOPE_PREFIX,
    KnowledgeScope,
    ResolvedScope,
    project_scope_name,
    scope_kind_of,
)
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import ResourceRef

#: Injected helpers (so the resolver stays free of filesystem imports).
GitRootFn = Callable[[str], "Path | None"]
ProjectUlidFn = Callable[[str], str]
#: ``scope resource name -> ~/.coffer/knowledge/<scope>/``.
ScopeDirFn = Callable[[str], "Path"]
#: Records ``scope_name -> project_root`` at provisioning time.
RecordRootFn = Callable[[str, str], Awaitable[None]]
#: One-time adoption of a legacy (path-derived) scope under the portable id.
MigrateStoreFn = Callable[[str, str, str], Awaitable[None]]
#: The surviving scope name for a merged-away project identity (or None).
AliasTargetFn = Callable[[str], Awaitable["str | None"]]

#: A project scope name: ``project-<26-char Crockford base32 id>``.
_PROJECT_SCOPE_NAME = re.compile(rf"^{PROJECT_SCOPE_PREFIX}[0-9A-HJKMNP-TV-Z]{{26}}$")
#: Any scope name must survive being used as one path segment.
_SAFE_SCOPE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def is_project_scope_name(name: str) -> bool:
    """Whether ``name`` is a well-formed ``project-<ULID>`` scope name.

    The ``project-`` prefix-stripping helpers must never see a mangled name, so
    every caller that recovers a ULID from a name checks this first.
    """
    return bool(_PROJECT_SCOPE_NAME.match(name))


def is_valid_scope_name(name: str) -> bool:
    """Whether ``name`` has a shape a knowledge scope can legally carry.

    ``global`` and a well-formed ``project-<ULID>`` always qualify; any other
    name qualifies as a named collection when it is a single safe path segment
    (it becomes a directory under ``~/.coffer/knowledge/``). A ``project-``
    name that is NOT a valid ULID is rejected outright — it would otherwise
    masquerade as a project scope.
    """
    if name == GLOBAL_SCOPE_NAME:
        return True
    if name.startswith(PROJECT_SCOPE_PREFIX):
        return is_project_scope_name(name)
    return bool(_SAFE_SCOPE_NAME.match(name)) and name not in {".", ".."}


class ScopeResolver:
    """Resolves scopes to scope dirs, provisioning the two auto-scopes."""

    def __init__(
        self,
        *,
        resources: ResourceService,
        git_root: GitRootFn,
        project_ulid: ProjectUlidFn,
        scope_dir: ScopeDirFn,
        record_project_root: RecordRootFn | None = None,
        legacy_project_ulid: ProjectUlidFn | None = None,
        migrate_store: MigrateStoreFn | None = None,
        merged_alias_target: AliasTargetFn | None = None,
    ) -> None:
        self._resources = resources
        self._git_root = git_root
        self._project_ulid = project_ulid
        self._scope_dir = scope_dir
        self._legacy_project_ulid = legacy_project_ulid
        self._migrate_store = migrate_store
        self._merged_alias_target = merged_alias_target
        # Optional persistence hook: when a project scope is provisioned, record
        # its originating git-root so the surface can echo it back.
        self._record_project_root = record_project_root

    async def resolve(
        self, *, scope: KnowledgeScope, cwd: str | None, name: str | None = None
    ) -> ResolvedScope:
        """Resolve one scope, provisioning the Resource for the two auto-scopes.

        ``name`` is required for ``KnowledgeScope.NAMED`` and ignored otherwise.
        """
        if scope is KnowledgeScope.GLOBAL:
            return await self._resolve_global()
        if scope is KnowledgeScope.NAMED:
            if name is None:
                raise ScopeUnresolved("<unnamed collection>")
            return await self.resolve_named(name)
        return await self._resolve_project(cwd)

    async def resolve_by_name(self, scope_name: str) -> ResolvedScope:
        """Resolve an existing scope from its resource name alone.

        The name says which of the three it is, so this is the entry point for
        every by-name surface (a REST path segment, a CLI argument)."""
        kind = scope_kind_of(scope_name)
        if kind is KnowledgeScope.GLOBAL:
            return await self._resolve_global()
        if kind is KnowledgeScope.NAMED:
            return await self.resolve_named(scope_name)
        if not is_project_scope_name(scope_name):
            raise ResourceNotFound(KIND_KNOWLEDGE, scope_name)
        return ResolvedScope(
            scope=KnowledgeScope.PROJECT,
            project_id=scope_name[len(PROJECT_SCOPE_PREFIX) :],
            store_dir=self._scope_dir(scope_name),
            resource_name=scope_name,
        )

    async def resolve_named(self, name: str) -> ResolvedScope:
        """Resolve a user-created collection. **Never provisions.**

        A named collection is deliberate, so an unknown name is an error and
        not an invitation to create one."""
        ref = ResourceRef(kind=KIND_KNOWLEDGE, name=name)
        if not is_valid_scope_name(name):
            raise ResourceNotFound(KIND_KNOWLEDGE, name)
        await self._resources.get(ref)  # raises ResourceNotFound when absent
        return ResolvedScope(
            scope=KnowledgeScope.NAMED,
            project_id=name,
            store_dir=self._scope_dir(name),
            resource_name=name,
        )

    async def resolve_recall_scopes(self, *, cwd: str | None) -> list[ResolvedScope]:
        """Scopes a default ``recall`` spans: project (if resolvable) + global."""
        scopes: list[ResolvedScope] = []
        if cwd is not None and self._git_root(cwd) is not None:
            scopes.append(await self._resolve_project(cwd))
        scopes.append(await self._resolve_global())
        return scopes

    # ----- internals -----

    async def _resolve_global(self) -> ResolvedScope:
        await self._ensure_scope(GLOBAL_SCOPE_NAME)
        return ResolvedScope(
            scope=KnowledgeScope.GLOBAL,
            project_id=WORKSPACE_GLOBAL_PROJECT_ID,
            store_dir=self._scope_dir(GLOBAL_SCOPE_NAME),
            resource_name=GLOBAL_SCOPE_NAME,
        )

    async def _resolve_project(self, cwd: str | None) -> ResolvedScope:
        if cwd is None:
            raise ScopeUnresolved("<none>")
        root = self._git_root(cwd)
        if root is None:
            raise ScopeUnresolved(cwd)
        project_id = self._project_ulid(str(root))
        project_id = await self._maybe_redirect_merged(project_id)
        scope_name = project_scope_name(project_id)
        await self._maybe_migrate_legacy(str(root), project_id)
        await self._ensure_scope(scope_name)
        if self._record_project_root is not None:
            await self._record_project_root(scope_name, str(root))
        return ResolvedScope(
            scope=KnowledgeScope.PROJECT,
            project_id=project_id,
            store_dir=self._scope_dir(scope_name),
            resource_name=scope_name,
        )

    async def _maybe_redirect_merged(self, project_id: str) -> str:
        """A merged-away identity resolves to its surviving scope.

        Consulted only on a MISS — when the computed identity's own scope
        still exists the hot path is untouched. Returns the (possibly
        redirected) project id."""
        if self._merged_alias_target is None:
            return project_id
        try:
            await self._resources.get(ResourceRef(KIND_KNOWLEDGE, project_scope_name(project_id)))
            return project_id  # the scope exists — no redirect
        except ResourceNotFound:
            pass
        target = await self._merged_alias_target(project_id)
        if target is None or not is_project_scope_name(target):
            return project_id
        return target[len(PROJECT_SCOPE_PREFIX) :]

    async def _maybe_migrate_legacy(self, root: str, project_id: str) -> None:
        """Adopt a surviving pre-portable-identity scope: same repo, old
        path-derived id. The portable scope already existing is NOT a reason
        to skip — on a second synced machine the portable scope arrives via
        an import while that machine's own legacy scope (different path,
        different id) still holds its entries; adoption merges them in
        additively (ADR-043)."""
        if self._legacy_project_ulid is None or self._migrate_store is None:
            return
        legacy_id = self._legacy_project_ulid(root)
        if legacy_id == project_id:
            return
        try:
            await self._resources.get(ResourceRef(KIND_KNOWLEDGE, project_scope_name(legacy_id)))
        except ResourceNotFound:
            return  # nothing to adopt
        await self._migrate_store(legacy_id, project_id, root)

    async def _ensure_scope(self, scope_name: str) -> None:
        ref = ResourceRef(kind=KIND_KNOWLEDGE, name=scope_name)
        try:
            await self._resources.get(ref)
            return
        except ResourceNotFound:
            pass
        # Provision with defaults (keyword + grep, offline, no embedding).
        await self._resources.register(
            kind=KIND_KNOWLEDGE,
            name=scope_name,
            config=KnowledgeConfig().model_dump(mode="json"),
            actor="system",
            description=("Global agent knowledge" if scope_name == GLOBAL_SCOPE_NAME else None),
        )


__all__ = [
    "GLOBAL_SCOPE_NAME",
    "KIND_KNOWLEDGE",
    "ScopeResolver",
    "is_project_scope_name",
    "is_valid_scope_name",
    "project_scope_name",
]
