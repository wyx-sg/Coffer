"""Memory scope value objects (spec 007).

Two scopes: ``global`` (the installation-global sentinel project id) and
``project`` (a project ULID resolved from the agent's cwd). ``ResolvedScope``
carries the resolution result; the on-disk ``store_dir`` is filled by
``infrastructure/memory/paths.py`` (domain stays path-engine-free, but the
field type is ``pathlib.Path``, which is stdlib and pure).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from coffer.domain.knowledge.document import WORKSPACE_GLOBAL_PROJECT_ID

__all__ = ["WORKSPACE_GLOBAL_PROJECT_ID", "MemoryScope", "ResolvedScope"]


class MemoryScope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"


@dataclass(frozen=True)
class ResolvedScope:
    """The outcome of resolving a requested scope to a concrete store."""

    scope: MemoryScope
    project_id: str  # ULID; the global sentinel for GLOBAL
    store_dir: Path  # ~/.coffer/memory/global | projects/<ulid>

    @property
    def is_global(self) -> bool:
        return self.scope is MemoryScope.GLOBAL
