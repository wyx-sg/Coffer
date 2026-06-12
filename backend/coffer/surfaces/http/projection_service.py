"""Composition-root projection service (spec 007).

This module lives outside the per-kind subpackages, so it is permitted to import
BOTH the memory kind and the agent kind (the per-kind import contracts fence the
kinds off from each other, not the composition root). It bridges the two:

- the **memory** side gives the canonical store directory + the facts, which we
  render to markdown;
- the **agent** side's :class:`ProjectionEngine` performs the native projection
  (symlink / managed block) via the right adapter.

It records each established projection in the binding repo so memory changes can
re-render and the agent-detail surfaces can list/remove a binding.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from coffer.application.agent.native_memory import (
    NativeMemoryProject,
    decode_claude_slug,
    scan_claude_native_memory,
)
from coffer.application.agent.projection import (
    CanonicalMemory,
    MemoryLayer,
    ProjectionEngine,
    ProjectionMode,
    ProjectionResult,
)
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.memory.scope import GLOBAL_STORE_NAME
from coffer.application.memory.service import MemoryService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.agent.projection_persistence import (
    ProjectionBinding,
    ProjectionBindingRepo,
)

_logger = logging.getLogger(__name__)

#: Resolves an absolute project root to the memory-store name Coffer keys it by
#: (provisioning the store if needed). Injected so the projection service stays
#: free of the scope-resolution wiring.
StoreForRootFn = Callable[[str], Awaitable[str]]


@dataclass
class TakeoverItem:
    """The outcome of attempting to take over one native project memory dir."""

    slug: str
    fact_count: int
    status: str  # imported | skipped_managed | skipped_undecodable | error
    project_root: str | None = None
    store_name: str | None = None
    backup_dir: str | None = None
    detail: str | None = None


@dataclass
class TakeoverResult:
    items: list[TakeoverItem]
    imported: int
    skipped: int


def _backup_memory_dir(mem: Path, suffix: str) -> Path:
    """Copy ``mem`` to a sibling ``<name>.bak-<suffix>`` before takeover touches
    it (the migration only moves files, but this is real user data — keep a full
    copy). Disambiguates with a counter if the backup name already exists."""
    base = mem.parent / f"{mem.name}.bak-{suffix}"
    backup = base
    n = 1
    while backup.exists():
        backup = mem.parent / f"{mem.name}.bak-{suffix}-{n}"
        n += 1
    shutil.copytree(mem, backup)
    return backup


def render_facts_markdown(facts: list[tuple[str, str]]) -> str:
    """Render facts to the canonical ``- [name](file) — description`` index body
    used inside an agent's managed block.

    ``facts`` is a list of ``(name, description)`` pairs (already ordered)."""
    lines = ["# Memory", ""]
    for name, description in facts:
        lines.append(f"- {name} — {description}" if description else f"- {name}")
    return "\n".join(lines).rstrip() + "\n"


class ProjectionService:
    """Establish / list / remove native memory projections for agents."""

    def __init__(
        self,
        *,
        memory: MemoryService,
        agents: AgentService,
        engine: ProjectionEngine,
        bindings: ProjectionBindingRepo,
        audit: AuditService | None = None,
        store_for_root: StoreForRootFn | None = None,
    ) -> None:
        self._memory = memory
        self._agents = agents
        self._engine = engine
        self._bindings = bindings
        self._audit = audit
        self._store_for_root = store_for_root

    async def _record(self, event: str, store_name: str, details: dict[str, object]) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            event,
            ref=ResourceRef("memory", store_name),
            actor="user",
            details=details,
        )

    async def _canonical_memory(self, store_name: str) -> CanonicalMemory:
        resolved = await self._memory.resolved_store(store_name)
        layer = MemoryLayer.GLOBAL if store_name == GLOBAL_STORE_NAME else MemoryLayer.PROJECT
        facts, _ = await self._memory.list_facts(store_name=store_name, limit=10_000, offset=0)
        rendered = render_facts_markdown([(f.name, f.description) for f in facts])
        return CanonicalMemory(store_dir=resolved.store_dir, rendered=rendered, layer=layer)

    async def establish(
        self, *, store_name: str, agent_ref: str, project_root: str | None
    ) -> ProjectionResult:
        agent = await self._agents.get(agent_ref)  # raises ResourceNotFound
        cfg = AgentConfig.model_validate(agent.config)
        await self._memory.ensure_store(store_name)
        memory = await self._canonical_memory(store_name)
        # The engine does synchronous filesystem work (migrate + symlink /
        # managed-block writes) — keep it off the event loop.
        result = await asyncio.to_thread(
            self._engine.establish,
            agent_type=cfg.type,
            agent_ref=agent_ref,
            memory=memory,
            project_root=project_root,
        )
        await self._bindings.upsert(
            ProjectionBinding(
                store_name=store_name,
                agent_ref=agent_ref,
                projection_mode=result.projection_mode.value,
                target_path=result.target_path,
                native_memory_disabled=result.native_memory_disabled,
            )
        )
        await self._record(
            AuditEventType.MEMORY_PROJECTED.value,
            store_name,
            {
                "agent_ref": agent_ref,
                "projection_mode": result.projection_mode.value,
                "target_path": result.target_path,
                "action": "established",
            },
        )
        return result

    async def take_over_claude_native_memory(
        self, *, agent_ref: str, backup_suffix: str
    ) -> TakeoverResult:
        """Take over every UNMANAGED Claude Code project memory dir Coffer finds.

        For each ``<config_dir>/projects/<slug>/memory`` not already a symlink:
        decode the slug back to a real project root (filesystem-guided, never
        guessed — undecodable slugs are reported and left untouched), back the
        dir up, provision the project's canonical store, then ``establish`` a
        SYMLINK projection (which migrates the existing facts in first). The
        agent must be Claude Code; other types yield an empty result."""
        if self._store_for_root is None:
            raise RuntimeError("store_for_root resolver not configured")
        agent = await self._agents.get(agent_ref)  # raises ResourceNotFound
        cfg = AgentConfig.model_validate(agent.config)
        if cfg.type is not AgentType.CLAUDE_CODE:
            return TakeoverResult(items=[], imported=0, skipped=0)
        config_dir = cfg.resolved_config_dir()
        projects = await asyncio.to_thread(scan_claude_native_memory, config_dir)
        items: list[TakeoverItem] = []
        for proj in projects:
            if proj.managed:
                continue  # already a Coffer symlink — nothing to take over.
            items.append(await self._take_over_one(proj, agent_ref, backup_suffix))
        imported = sum(1 for i in items if i.status == "imported")
        return TakeoverResult(items=items, imported=imported, skipped=len(items) - imported)

    async def _take_over_one(
        self, proj: NativeMemoryProject, agent_ref: str, backup_suffix: str
    ) -> TakeoverItem:
        slug = proj.slug
        fact_count = proj.fact_count
        mem = Path(proj.memory_dir)
        project_root = decode_claude_slug(slug)
        if project_root is None:
            return TakeoverItem(
                slug=slug,
                fact_count=fact_count,
                status="skipped_undecodable",
                detail="slug does not map to any existing path",
            )
        try:
            assert self._store_for_root is not None
            backup = await asyncio.to_thread(_backup_memory_dir, mem, backup_suffix)
            store_name = await self._store_for_root(str(project_root))
            await self.establish(
                store_name=store_name, agent_ref=agent_ref, project_root=str(project_root)
            )
        except (OSError, ValueError) as exc:
            _logger.warning(
                "projection.takeover.failed",
                extra={"slug": slug, "project_root": str(project_root)},
                exc_info=True,
            )
            return TakeoverItem(
                slug=slug,
                fact_count=fact_count,
                status="error",
                project_root=str(project_root),
                detail=str(exc),
            )
        return TakeoverItem(
            slug=slug,
            fact_count=fact_count,
            status="imported",
            project_root=str(project_root),
            store_name=store_name,
            backup_dir=str(backup),
        )

    async def list_projections(self, *, store_name: str) -> list[ProjectionBinding]:
        return await self._bindings.list_for_store(store_name)

    async def remove(self, *, store_name: str, agent_ref: str) -> bool:
        binding = await self._bindings.get(store_name, agent_ref)
        if binding is None:
            return False
        # Undo the native projection by the stored target path + mode (the
        # original project root is not retained — only the established target).
        # A failed undo KEEPS the binding row (deleting it would orphan the
        # symlink/managed block forever) and propagates, so the caller sees the
        # failure and can retry.
        try:
            await asyncio.to_thread(
                self._engine.remove_target,
                mode=ProjectionMode(binding.projection_mode),
                target_path=binding.target_path,
            )
        except (ValueError, OSError):
            _logger.warning(
                "projection.remove.native_undo_failed",
                extra={"store": store_name, "agent": agent_ref, "target": binding.target_path},
                exc_info=True,
            )
            raise
        deleted = await self._bindings.delete(store_name, agent_ref)
        if deleted:
            await self._record(
                AuditEventType.MEMORY_PROJECTED.value,
                store_name,
                {
                    "agent_ref": agent_ref,
                    "projection_mode": binding.projection_mode,
                    "target_path": binding.target_path,
                    "action": "removed",
                },
            )
        return deleted

    async def remove_all_for_store(self, *, store_name: str) -> None:
        """Remove every projection of a store (native target + binding row).

        Wired into the memory kind's ``on_delete`` so deleting a store does not
        leave dangling symlinks / managed blocks + binding rows behind
        (finding #6). Here a failed native undo is logged but the binding row is
        still deleted — the store itself is going away, so a row pointing at it
        would dangle."""
        for binding in await self._bindings.list_for_store(store_name):
            try:
                await asyncio.to_thread(
                    self._engine.remove_target,
                    mode=ProjectionMode(binding.projection_mode),
                    target_path=binding.target_path,
                )
            except (ValueError, OSError):
                _logger.warning(
                    "projection.remove_all.native_undo_failed",
                    extra={
                        "store": store_name,
                        "agent": binding.agent_ref,
                        "target": binding.target_path,
                    },
                    exc_info=True,
                )
            await self._bindings.delete(store_name, binding.agent_ref)

    async def rerender_for_store(self, *, store_name: str) -> None:
        """Re-render every projection of a store (called on memory change).

        Refreshes each binding in place at its stored ``target_path`` + mode, so
        a Codex PROJECT binding's managed block refreshes without re-deriving the
        original project root (re-``establish``-ing with ``project_root=None``
        raised ValueError for a Codex project binding and silently went stale —
        finding #4). SYMLINK bindings need no rewrite (the symlink points at the
        canonical store)."""
        bindings = await self._bindings.list_for_store(store_name)
        if not bindings:
            return
        memory = await self._canonical_memory(store_name)
        for binding in bindings:
            try:
                await asyncio.to_thread(
                    self._engine.rerender_target,
                    mode=ProjectionMode(binding.projection_mode),
                    target_path=binding.target_path,
                    rendered=memory.rendered,
                )
            except (ValueError, OSError):
                # A stale managed block is agent-visible state; never silent.
                _logger.warning(
                    "projection.rerender_failed",
                    extra={
                        "store": store_name,
                        "agent": binding.agent_ref,
                        "target": binding.target_path,
                    },
                    exc_info=True,
                )
