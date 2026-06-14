"""RENDER memory adapters for OpenCode, OpenClaw, and Hermes (spec 007).

These three agents project shared memory through a marker-fenced **managed
block** (``ProjectionMode.RENDER``), mirroring the Codex reference adapter in
:mod:`coffer.application.agent.projection.adapters`. They consume only canonical
paths + rendered markdown (a :class:`CanonicalMemory`) — never the memory kind's
types — so the agent layer stays fenced off from the memory kind (Contract 5b).

Unlike Codex, none of these disable a native-memory channel: OpenCode has no
native memory store to disable, and OpenClaw/Hermes own native stores that Coffer
deliberately leaves alone (it owns only its managed block).

- **OpenCode** → ``RENDER``: a managed block in ``<project>/AGENTS.md`` (project)
  and ``~/.config/opencode/AGENTS.md`` (global). OpenCode reads ``AGENTS.md``.
- **OpenClaw** → ``RENDER``: a managed block in ``<project>/MEMORY.md`` (project)
  and ``~/.openclaw/MEMORY.md`` (global).
- **Hermes** → ``RENDER``: one bounded managed-block file per scope inside the
  global ``memories/`` store — ``coffer-global.md`` (global) and
  ``coffer-<slug>.md`` (project).
"""

from __future__ import annotations

from pathlib import Path

from coffer.application.agent.projection.adapters import claude_project_slug
from coffer.application.agent.projection.types import (
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
    CanonicalMemory,
    MemoryLayer,
    ProjectionFs,
    ProjectionMode,
    ProjectionResult,
)
from coffer.domain.agent.types import AgentType


class OpenCodeMemoryAdapter:
    """Renders a managed block into OpenCode's ``AGENTS.md`` (project + global).

    Mirrors the Codex adapter but does NOT disable any native memory: OpenCode
    has no native memory store, and ``AGENTS.md`` is its documented instruction
    surface.
    """

    agent_type = AgentType.OPENCODE
    projection_mode = ProjectionMode.RENDER

    def __init__(self, fs: ProjectionFs, *, config_dir: Path | None = None) -> None:
        self._fs = fs
        self._config_dir = config_dir or AgentType.OPENCODE.config_dir()

    def memory_location(self, *, project_root: str | None, layer: MemoryLayer) -> Path:
        if layer is MemoryLayer.PROJECT:
            if project_root is None:
                raise ValueError("OpenCode project projection requires a project root")
            return Path(project_root) / "AGENTS.md"
        return self._config_dir / "AGENTS.md"

    def establish(
        self, *, memory: CanonicalMemory, project_root: str | None, agent_ref: str
    ) -> ProjectionResult:
        target = self.memory_location(project_root=project_root, layer=memory.layer)
        self._fs.write_managed_block(
            file_path=target,
            block_body=memory.rendered,
            start_marker=MANAGED_BLOCK_START,
            end_marker=MANAGED_BLOCK_END,
        )
        return ProjectionResult(
            agent_ref=agent_ref,
            projection_mode=ProjectionMode.RENDER,
            target_path=str(target),
            native_memory_disabled=False,
            merged_existing=False,
        )

    def remove(self, *, project_root: str | None, layer: MemoryLayer) -> None:
        target = self.memory_location(project_root=project_root, layer=layer)
        self._fs.strip_managed_block(
            file_path=target,
            start_marker=MANAGED_BLOCK_START,
            end_marker=MANAGED_BLOCK_END,
        )

    def render(self, facts_markdown: str) -> bytes:
        return facts_markdown.encode("utf-8")


class OpenClawMemoryAdapter:
    """Renders a managed block into OpenClaw's ``MEMORY.md`` (project + global).

    OpenClaw also keeps a ``memory/*.md`` index that it populates itself; that
    index is read-only from Coffer's perspective and is never touched. Coffer
    owns ONLY the managed block in ``MEMORY.md`` (content outside the markers,
    and the whole ``memory/`` index dir, are left intact). The on-disk
    ``MEMORY.md`` format is only semi-documented, so we keep to the safe
    managed-block-in-``MEMORY.md`` approach rather than reformatting the index.
    """

    agent_type = AgentType.OPENCLAW
    projection_mode = ProjectionMode.RENDER

    def __init__(self, fs: ProjectionFs, *, config_dir: Path | None = None) -> None:
        self._fs = fs
        self._config_dir = config_dir or AgentType.OPENCLAW.config_dir()

    def memory_location(self, *, project_root: str | None, layer: MemoryLayer) -> Path:
        if layer is MemoryLayer.PROJECT:
            if project_root is None:
                raise ValueError("OpenClaw project projection requires a project root")
            return Path(project_root) / "MEMORY.md"
        return self._config_dir / "MEMORY.md"

    def establish(
        self, *, memory: CanonicalMemory, project_root: str | None, agent_ref: str
    ) -> ProjectionResult:
        target = self.memory_location(project_root=project_root, layer=memory.layer)
        self._fs.write_managed_block(
            file_path=target,
            block_body=memory.rendered,
            start_marker=MANAGED_BLOCK_START,
            end_marker=MANAGED_BLOCK_END,
        )
        return ProjectionResult(
            agent_ref=agent_ref,
            projection_mode=ProjectionMode.RENDER,
            target_path=str(target),
            native_memory_disabled=False,
            merged_existing=False,
        )

    def remove(self, *, project_root: str | None, layer: MemoryLayer) -> None:
        target = self.memory_location(project_root=project_root, layer=layer)
        self._fs.strip_managed_block(
            file_path=target,
            start_marker=MANAGED_BLOCK_START,
            end_marker=MANAGED_BLOCK_END,
        )

    def render(self, facts_markdown: str) -> bytes:
        return facts_markdown.encode("utf-8")


class HermesMemoryAdapter:
    """Renders a managed block into ONE bounded file per scope in Hermes'
    ``memories/`` store.

    Hermes' memory is a global ``memories/*.md`` store that is size-capped and
    injection-scanned at load. To respect the per-file size cap and avoid
    scattering Coffer's footprint across the store, Coffer owns exactly one
    bounded file per scope — ``coffer-global.md`` for the global scope and
    ``coffer-<slug>.md`` for a project scope — and writes its facts only between
    the managed markers inside that single file. Hermes' own ``memories/*.md``
    files are never touched.
    """

    agent_type = AgentType.HERMES
    projection_mode = ProjectionMode.RENDER

    def __init__(self, fs: ProjectionFs, *, config_dir: Path | None = None) -> None:
        self._fs = fs
        self._config_dir = config_dir or AgentType.HERMES.config_dir()

    def memory_location(self, *, project_root: str | None, layer: MemoryLayer) -> Path:
        memories = self._config_dir / "memories"
        if layer is MemoryLayer.PROJECT:
            if project_root is None:
                raise ValueError("Hermes project projection requires a project root")
            return memories / f"coffer-{claude_project_slug(project_root)}.md"
        return memories / "coffer-global.md"

    def establish(
        self, *, memory: CanonicalMemory, project_root: str | None, agent_ref: str
    ) -> ProjectionResult:
        target = self.memory_location(project_root=project_root, layer=memory.layer)
        self._fs.write_managed_block(
            file_path=target,
            block_body=memory.rendered,
            start_marker=MANAGED_BLOCK_START,
            end_marker=MANAGED_BLOCK_END,
        )
        return ProjectionResult(
            agent_ref=agent_ref,
            projection_mode=ProjectionMode.RENDER,
            target_path=str(target),
            native_memory_disabled=False,
            merged_existing=False,
        )

    def remove(self, *, project_root: str | None, layer: MemoryLayer) -> None:
        target = self.memory_location(project_root=project_root, layer=layer)
        self._fs.strip_managed_block(
            file_path=target,
            start_marker=MANAGED_BLOCK_START,
            end_marker=MANAGED_BLOCK_END,
        )

    def render(self, facts_markdown: str) -> bytes:
        return facts_markdown.encode("utf-8")


__all__ = [
    "HermesMemoryAdapter",
    "OpenClawMemoryAdapter",
    "OpenCodeMemoryAdapter",
]
