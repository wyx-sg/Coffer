"""ProjectionEngine — dispatch memory projection on the adapter's mode.

Lives in the agent layer (FR-011/014). The engine selects the right
:class:`AgentMemoryAdapter` for an agent type and, given a
:class:`CanonicalMemory` hand-off from the composition root, performs the native
projection (symlink / managed block) and records the binding so memory changes
can re-render it. The memory substrate is never imported here — the composition
root renders the facts to markdown and resolves the canonical store dir, then
passes them in.
"""

from __future__ import annotations

from coffer.application.agent.projection.adapters import (
    AgentMemoryAdapter,
    ClaudeCodeMemoryAdapter,
    CodexMemoryAdapter,
)
from coffer.application.agent.projection.types import (
    CanonicalMemory,
    MemoryLayer,
    ProjectionFs,
    ProjectionMode,
    ProjectionResult,
)
from coffer.domain.agent.types import AgentType


def default_adapters(fs: ProjectionFs) -> dict[AgentType, AgentMemoryAdapter]:
    """The built-in adapter registry (one per supported agent type), each given
    the injected filesystem port."""
    return {
        AgentType.CLAUDE_CODE: ClaudeCodeMemoryAdapter(fs),
        AgentType.CODEX: CodexMemoryAdapter(fs),
    }


class ProjectionEngine:
    """Dispatches projection establish/remove on the adapter's mode.

    Adding a new agent requires only a new adapter in the registry (SC-005); the
    engine and the memory substrate are unchanged. The filesystem port is
    injected (the composition root supplies the infrastructure adapter) so the
    application layer never imports infrastructure (Contract 2b).
    """

    def __init__(
        self,
        fs: ProjectionFs,
        *,
        adapters: dict[AgentType, AgentMemoryAdapter] | None = None,
    ) -> None:
        self._fs = fs
        self._adapters = adapters or default_adapters(fs)

    def adapter_for(self, agent_type: AgentType) -> AgentMemoryAdapter:
        adapter = self._adapters.get(agent_type)
        if adapter is None:
            raise KeyError(f"no memory adapter for agent type {agent_type!r}")
        return adapter

    def projection_mode(self, agent_type: AgentType) -> ProjectionMode:
        return self.adapter_for(agent_type).projection_mode

    def establish(
        self,
        *,
        agent_type: AgentType,
        agent_ref: str,
        memory: CanonicalMemory,
        project_root: str | None,
    ) -> ProjectionResult:
        """Establish (or refresh) the projection. NONE-mode adapters are a
        no-op that still returns a (disabled) result for surface reporting."""
        adapter = self.adapter_for(agent_type)
        if adapter.projection_mode is ProjectionMode.NONE:
            return ProjectionResult(
                agent_ref=agent_ref,
                projection_mode=ProjectionMode.NONE,
                target_path="",
                native_memory_disabled=False,
            )
        return adapter.establish(memory=memory, project_root=project_root, agent_ref=agent_ref)

    def remove(
        self,
        *,
        agent_type: AgentType,
        project_root: str | None,
        layer: MemoryLayer,
    ) -> None:
        adapter = self.adapter_for(agent_type)
        if adapter.projection_mode is ProjectionMode.NONE:
            return
        adapter.remove(project_root=project_root, layer=layer)

    def remove_target(self, *, mode: ProjectionMode, target_path: str) -> None:
        """Undo a projection by its stored native target path + mode.

        Used on un-projection when the original project root is no longer known
        (only the established target path was persisted). SYMLINK targets are
        unlinked; RENDER targets have their managed block stripped; NONE is a
        no-op."""
        from pathlib import Path

        from coffer.application.agent.projection.types import (
            MANAGED_BLOCK_END,
            MANAGED_BLOCK_START,
        )

        if not target_path:
            return
        path = Path(target_path)
        if mode is ProjectionMode.SYMLINK:
            self._fs.remove_symlink(link_path=path)
        elif mode is ProjectionMode.RENDER:
            self._fs.strip_managed_block(
                file_path=path,
                start_marker=MANAGED_BLOCK_START,
                end_marker=MANAGED_BLOCK_END,
            )

    def rerender_target(self, *, mode: ProjectionMode, target_path: str, rendered: str) -> None:
        """Refresh a projection in place by its stored target path + mode.

        A RENDER target's managed block is rewritten at the stored path (this is
        what keeps a Codex ``<project>/AGENTS.md`` block current without knowing
        the original project root — finding #4). A SYMLINK target needs no
        rewrite: facts are written to the canonical store the symlink points at,
        so the agent already sees the change. NONE is a no-op."""
        from pathlib import Path

        from coffer.application.agent.projection.types import (
            MANAGED_BLOCK_END,
            MANAGED_BLOCK_START,
        )

        if not target_path or mode is not ProjectionMode.RENDER:
            return
        self._fs.write_managed_block(
            file_path=Path(target_path),
            block_body=rendered,
            start_marker=MANAGED_BLOCK_START,
            end_marker=MANAGED_BLOCK_END,
        )
