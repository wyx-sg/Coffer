"""AgentNativeMemoryService — list a coding agent's OWN native memory stores.

Read-only. Resolves an agent to its :class:`AgentType`, looks up the native
per-project memory layout for that type (``domain/agent/native_memory.py``), and
scans the agent's config dir for ``<projects>/<slug>/<memory>`` directories via
a :class:`NativeMemoryScanPort`. An agent type with no known native layout
(Codex, etc.) — or a missing projects dir — yields an empty list, never an
error. A non-existent agent name raises ``ResourceNotFound`` (→ 404) via the
agent lookup.

Filesystem access goes through ``NativeMemoryScanPort`` (a Protocol this module
owns); the concrete adapter lives in
``infrastructure/agent/native_memory_store.py`` (Contract 2b: application defines
the port, infrastructure implements it).
"""

from __future__ import annotations

import pathlib
from typing import Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.native_memory import (
    NativeMemoryStore,
    native_memory_layout_for,
    resolve_project_slug,
)
from coffer.domain.resource import Resource


class NativeMemoryScanPort(Protocol):
    """Filesystem scan for native per-project memory. Implemented in infra."""

    def scan(self, projects_root: pathlib.Path, memory_subdir: str) -> list[tuple[str, str, int]]:
        """Return ``(slug, memory_dir_abs, item_count)`` per project that has a
        memory directory under ``projects_root``."""
        ...


# Structural type for the agent-lookup dependency — avoids a hard import of
# AgentService (and keeps this service unit-testable with a fake).
class _AgentLookup(Protocol):
    async def get(self, name: str) -> Resource: ...


class AgentNativeMemoryService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        scanner: NativeMemoryScanPort,
    ) -> None:
        self._agents = agent_service
        self._scanner = scanner

    async def list_stores(self, name: str) -> list[NativeMemoryStore]:
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        cfg = AgentConfig.model_validate((await self._agents.get(name)).config)
        layout = native_memory_layout_for(cfg.type)
        if layout is None:
            return []
        projects_root = cfg.resolved_config_dir() / layout.projects_subdir
        scans = self._scanner.scan(projects_root, layout.memory_subdir)
        result = [
            self._to_store(slug, memory_dir, item_count) for slug, memory_dir, item_count in scans
        ]
        return sorted(result, key=lambda s: (-s.item_count, s.project_label))

    @staticmethod
    def _to_store(slug: str, memory_dir: str, item_count: int) -> NativeMemoryStore:
        # FS-aware so a hyphenated project name (e.g. "wedding-invitation") is not
        # mistaken for a nested "wedding/invitation"; falls back to a lossy decode
        # when the real project dir is gone.
        label, path = resolve_project_slug(slug, lambda p: pathlib.Path(p).is_dir())
        return NativeMemoryStore(
            project_label=label,
            project_path=path,
            slug=slug,
            memory_dir=memory_dir,
            item_count=item_count,
        )
