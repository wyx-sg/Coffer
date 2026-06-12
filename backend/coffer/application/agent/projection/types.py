"""Projection value objects shared by the agent-side memory adapters (spec 007).

These live in the **agent layer** (FR-011/FR-014): the memory substrate stays
agent-agnostic and only hands over canonical paths + rendered markdown; the
adapters here own every native-file mutation. By Contract 5b the agent kind may
not import the memory kind, so nothing in this package imports
``coffer.*.memory`` — a projection is described purely by a canonical directory
path and a block of rendered markdown bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class ProjectionMode(StrEnum):
    """How an agent's native memory surface is fed from the canonical store."""

    SYMLINK = "SYMLINK"
    RENDER = "RENDER"
    NONE = "NONE"


class MemoryLayer(StrEnum):
    """Which scope layer is being projected into the agent."""

    GLOBAL = "global"
    PROJECT = "project"


# Managed-block markers for RENDER-mode adapters (Codex). Content OUTSIDE these
# markers is never touched; the block between them is rewritten idempotently.
MANAGED_BLOCK_START = "<!-- coffer:memory:start (managed, do not edit) -->"
MANAGED_BLOCK_END = "<!-- coffer:memory:end -->"


@dataclass(frozen=True)
class ProjectionResult:
    """The outcome of establishing (or refreshing) one projection."""

    agent_ref: str
    projection_mode: ProjectionMode
    target_path: str
    native_memory_disabled: bool
    merged_existing: bool = False


@dataclass(frozen=True)
class SymlinkOutcome:
    """Result of establishing a directory symlink projection."""

    target_path: str
    merged_existing: bool


class ProjectionFs(Protocol):
    """The filesystem operations the adapters need (a port).

    The concrete implementation lives in ``infrastructure.agent.projection_fs``
    and is injected at the composition root, so the agent **application** layer
    never imports infrastructure directly (Contract 2b)."""

    def symlink_with_migrate(self, *, canonical_dir: Path, link_path: Path) -> SymlinkOutcome: ...
    def remove_symlink(self, *, link_path: Path) -> None: ...
    def write_managed_block(
        self, *, file_path: Path, block_body: str, start_marker: str, end_marker: str
    ) -> str: ...
    def strip_managed_block(
        self, *, file_path: Path, start_marker: str, end_marker: str
    ) -> None: ...
    def disable_codex_memory(self, *, config_path: Path) -> bool:
        """Set ``[memories] enabled = false`` in Codex's config.toml,
        idempotently. Returns whether native memory is (now) disabled."""
        ...


@dataclass(frozen=True)
class CanonicalMemory:
    """The substrate's hand-off to an adapter: the canonical store directory
    (source of truth) plus the markdown already rendered from the facts.

    ``store_dir`` is the canonical per-scope memory directory. ``rendered`` is
    the markdown an adapter writes into a managed block (RENDER mode); SYMLINK
    adapters ignore it and point straight at ``store_dir``.
    """

    store_dir: Path
    rendered: str
    layer: MemoryLayer
