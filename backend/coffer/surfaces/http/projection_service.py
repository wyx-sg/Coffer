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

import contextlib

from coffer.application.agent.projection import (
    CanonicalMemory,
    MemoryLayer,
    ProjectionEngine,
    ProjectionMode,
    ProjectionResult,
)
from coffer.application.agent.service import AgentService
from coffer.application.memory.scope import GLOBAL_STORE_NAME
from coffer.application.memory.service import MemoryService
from coffer.domain.agent.config import AgentConfig
from coffer.infrastructure.agent.projection_persistence import (
    ProjectionBinding,
    ProjectionBindingRepo,
)


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
    ) -> None:
        self._memory = memory
        self._agents = agents
        self._engine = engine
        self._bindings = bindings

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
        result = self._engine.establish(
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
        return result

    async def list_projections(self, *, store_name: str) -> list[ProjectionBinding]:
        return await self._bindings.list_for_store(store_name)

    async def remove(self, *, store_name: str, agent_ref: str) -> bool:
        binding = await self._bindings.get(store_name, agent_ref)
        if binding is None:
            return False
        # Undo the native projection by the stored target path + mode (the
        # original project root is not retained — only the established target).
        with contextlib.suppress(ValueError, OSError):
            self._engine.remove_target(
                mode=ProjectionMode(binding.projection_mode),
                target_path=binding.target_path,
            )
        return await self._bindings.delete(store_name, agent_ref)

    async def remove_all_for_store(self, *, store_name: str) -> None:
        """Remove every projection of a store (native target + binding row).

        Wired into the memory kind's ``on_delete`` so deleting a store does not
        leave dangling symlinks / managed blocks + binding rows behind
        (finding #6)."""
        for binding in await self._bindings.list_for_store(store_name):
            await self.remove(store_name=store_name, agent_ref=binding.agent_ref)

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
            with contextlib.suppress(ValueError, OSError):
                self._engine.rerender_target(
                    mode=ProjectionMode(binding.projection_mode),
                    target_path=binding.target_path,
                    rendered=memory.rendered,
                )
