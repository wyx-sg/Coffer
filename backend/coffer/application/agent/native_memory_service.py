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
    CodexGlobalLayout,
    NativeMemoryStore,
    ScannedStore,
    native_memory_layout_for,
    resolve_project_slug,
)
from coffer.domain.resource import Resource


class NativeMemoryScanPort(Protocol):
    """Filesystem scan for native memory. Implemented in infra."""

    def scan(self, projects_root: pathlib.Path, memory_subdir: str) -> list[ScannedStore]:
        """Return a :class:`ScannedStore` per project that has a memory
        directory under ``projects_root`` (Claude Code's per-project layout)."""
        ...

    def scan_codex_global(self, memories_dir: pathlib.Path, index_file: str) -> list[ScannedStore]:
        """Return a :class:`ScannedStore` per distinct routed cwd in Codex's
        single global task-grouped store under ``memories_dir``."""
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
        config_dir = cfg.resolved_config_dir()
        if isinstance(layout, CodexGlobalLayout):
            # Codex: one global task-grouped document, one row per routed cwd.
            scans = self._scanner.scan_codex_global(
                config_dir / layout.memory_subdir, layout.index_file
            )
        else:
            # Claude Code: one row per project that has a memory/ dir.
            scans = self._scanner.scan(config_dir / layout.projects_subdir, layout.memory_subdir)
        result = [self._to_store(scan) for scan in scans]
        return sorted(result, key=lambda s: (-s.item_count, s.project_label))

    @staticmethod
    def _to_store(scan: ScannedStore) -> NativeMemoryStore:
        # The real project path from the session transcript is authoritative when
        # present (the slug encoding is lossy: a hyphenated segment or a "."/"_"
        # in the home dir collapses to "-" and cannot be reconstructed). Only when
        # no transcript recorded a cwd do we fall back to the FS-aware slug decode.
        if scan.project_path:
            path: str | None = scan.project_path
            label = pathlib.PurePath(scan.project_path).name or scan.project_path
        else:
            label, path = resolve_project_slug(scan.slug, lambda p: pathlib.Path(p).is_dir())
        return NativeMemoryStore(
            project_label=label,
            project_path=path,
            slug=scan.slug,
            memory_dir=scan.memory_dir,
            item_count=scan.item_count,
        )
