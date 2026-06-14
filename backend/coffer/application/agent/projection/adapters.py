"""Per-agent memory adapters (spec 007, FR-011/012/013).

Each adapter declares a :class:`ProjectionMode` and owns the native-file
mutations for one agent product. Adapters consume only canonical paths +
rendered markdown (a :class:`CanonicalMemory`) — never the memory kind's types
— so the agent layer stays fenced off from the memory kind (Contract 5b) and
the memory substrate stays agent-agnostic (FR-014).

- **Claude Code** → ``SYMLINK``: the project layer's canonical dir *becomes*
  Claude's ``~/.claude/projects/<slug>/memory/`` via a directory symlink
  (existing real files merged first). The global layer renders a managed block
  into ``~/.claude/CLAUDE.md``.
- **Codex** → ``RENDER``: a marker-fenced managed block in ``<project>/AGENTS.md``
  (project) and ``~/.codex/AGENTS.md`` (global); Codex native ``memories`` is
  disabled so no second copy accumulates.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

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

# Claude Code derives a per-project slug by replacing EACH non-alphanumeric
# character in the absolute project root with a single dash — runs are NOT
# collapsed (e.g. ``/Users/xing/Coffer`` → ``-Users-xing-Coffer``, and
# ``/Users/xing/.claude`` → ``-Users-xing--claude`` with a double dash). We
# mirror that so the symlink lands exactly where Claude looks for the project's
# memory; a ``+`` quantifier here would collapse consecutive separators and
# point at the wrong directory (finding #2).
_SLUG_NONALNUM = re.compile(r"[^A-Za-z0-9]")


def claude_project_slug(project_root: str | Path) -> str:
    """The ``~/.claude/projects/<slug>`` directory name for a project root."""
    absolute = str(Path(project_root))
    return _SLUG_NONALNUM.sub("-", absolute)


class AgentMemoryAdapter(Protocol):
    """The contract every agent's memory adapter implements."""

    agent_type: AgentType
    projection_mode: ProjectionMode

    def memory_location(self, *, project_root: str | None, layer: MemoryLayer) -> Path:
        """The native path this adapter owns for ``layer`` (symlink path for
        SYMLINK adapters; managed-block file for RENDER adapters)."""
        ...

    def establish(
        self, *, memory: CanonicalMemory, project_root: str | None, agent_ref: str
    ) -> ProjectionResult:
        """Establish (or refresh) the projection, performing all FS mutations."""
        ...

    def remove(self, *, project_root: str | None, layer: MemoryLayer) -> None:
        """Undo the projection (restore native state)."""
        ...

    def render(self, facts_markdown: str) -> bytes:
        """The bytes this adapter would write for ``facts_markdown`` (the
        managed-block body for RENDER; the rendered dir index for SYMLINK)."""
        ...


# --------------------------------------------------------------------------- #
# Claude Code — SYMLINK                                                        #
# --------------------------------------------------------------------------- #


class ClaudeCodeMemoryAdapter:
    """Projects project memory as a symlink; global memory as a CLAUDE.md block."""

    agent_type = AgentType.CLAUDE_CODE
    projection_mode = ProjectionMode.SYMLINK

    def __init__(self, fs: ProjectionFs, *, config_dir: Path | None = None) -> None:
        self._fs = fs
        self._config_dir = config_dir or AgentType.CLAUDE_CODE.config_dir()

    def memory_location(self, *, project_root: str | None, layer: MemoryLayer) -> Path:
        if layer is MemoryLayer.PROJECT:
            if project_root is None:
                raise ValueError("Claude project projection requires a project root")
            slug = claude_project_slug(project_root)
            return self._config_dir / "projects" / slug / "memory"
        return self._config_dir / "CLAUDE.md"

    def establish(
        self, *, memory: CanonicalMemory, project_root: str | None, agent_ref: str
    ) -> ProjectionResult:
        if memory.layer is MemoryLayer.PROJECT:
            link = self.memory_location(project_root=project_root, layer=memory.layer)
            outcome = self._fs.symlink_with_migrate(canonical_dir=memory.store_dir, link_path=link)
            return ProjectionResult(
                agent_ref=agent_ref,
                projection_mode=ProjectionMode.SYMLINK,
                target_path=outcome.target_path,
                native_memory_disabled=False,  # Claude auto-memory stays ON.
                merged_existing=outcome.merged_existing,
            )
        # Global layer → managed block in ~/.claude/CLAUDE.md (no symlink; the
        # global memory dir is not a Claude project dir).
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
        if layer is MemoryLayer.PROJECT:
            self._fs.remove_symlink(link_path=target)
        else:
            self._fs.strip_managed_block(
                file_path=target,
                start_marker=MANAGED_BLOCK_START,
                end_marker=MANAGED_BLOCK_END,
            )

    def render(self, facts_markdown: str) -> bytes:
        return facts_markdown.encode("utf-8")


# --------------------------------------------------------------------------- #
# Codex — RENDER                                                               #
# --------------------------------------------------------------------------- #


class CodexMemoryAdapter:
    """Renders a managed block into AGENTS.md and disables Codex native memory."""

    agent_type = AgentType.CODEX
    projection_mode = ProjectionMode.RENDER

    def __init__(self, fs: ProjectionFs, *, config_dir: Path | None = None) -> None:
        self._fs = fs
        self._config_dir = config_dir or AgentType.CODEX.config_dir()

    def memory_location(self, *, project_root: str | None, layer: MemoryLayer) -> Path:
        if layer is MemoryLayer.PROJECT:
            if project_root is None:
                raise ValueError("Codex project projection requires a project root")
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
        disabled = self._disable_native_memory()
        return ProjectionResult(
            agent_ref=agent_ref,
            projection_mode=ProjectionMode.RENDER,
            target_path=str(target),
            native_memory_disabled=disabled,
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

    def _disable_native_memory(self) -> bool:
        """Disable Codex native ``memories`` (config.toml) so no second copy
        accumulates. Delegated to the FS port (idempotent)."""
        return self._fs.disable_codex_memory(config_path=self._config_dir / "config.toml")


# --------------------------------------------------------------------------- #
# NONE — agents without native memory projection (yet)                         #
# --------------------------------------------------------------------------- #


class NoneMemoryAdapter:
    """A no-op adapter for agents that don't (yet) project shared memory.

    ``projection_mode`` is NONE, so the engine short-circuits establish/remove to
    a disabled result; the methods below are defensive no-ops. Agents that gain a
    real native-memory channel (e.g. OpenClaw ``MEMORY.md``, Hermes
    ``memories/``) replace this with a SYMLINK/RENDER adapter.
    """

    projection_mode = ProjectionMode.NONE

    def __init__(self, agent_type: AgentType) -> None:
        self.agent_type = agent_type

    def memory_location(self, *, project_root: str | None, layer: MemoryLayer) -> Path:
        # No native target; return a stable, unused sentinel path.
        return Path("/dev/null")

    def establish(
        self, *, memory: CanonicalMemory, project_root: str | None, agent_ref: str
    ) -> ProjectionResult:
        return ProjectionResult(
            agent_ref=agent_ref,
            projection_mode=ProjectionMode.NONE,
            target_path="",
            native_memory_disabled=False,
        )

    def remove(self, *, project_root: str | None, layer: MemoryLayer) -> None:
        return None

    def render(self, facts_markdown: str) -> bytes:
        return facts_markdown.encode("utf-8")


__all__ = [
    "AgentMemoryAdapter",
    "ClaudeCodeMemoryAdapter",
    "CodexMemoryAdapter",
    "NoneMemoryAdapter",
    "claude_project_slug",
]
