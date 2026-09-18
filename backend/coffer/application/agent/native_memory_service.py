"""AgentNativeMemoryService — read a coding agent's OWN native memory stores.

Read-only. Resolves an agent to its :class:`AgentType`, looks up the native
per-project memory layout for that type (``domain/agent/native_memory.py``), and
scans the agent's config dir for ``<projects>/<slug>/<memory>`` directories via
a :class:`NativeMemoryScanPort`. An agent type with no known native layout
— or a missing projects dir — yields an empty list, never an
error. A uid naming no registered agent raises ``ResourceNotFound`` (→ 404)
via the agent lookup.

Beyond the listing it also opens one store: its directory as a tree and one of
its files as text, which is what the store's detail page renders. A store is a
directory, so a tree plus a read-only preview is the shape that shows it without
interpreting it — the reader sees the same bytes the agent will.

That read has to be guarded, because the client names the directory. The guard
is ``is_native_memory_dir``: the candidate must be exactly the shape the layout
would have listed, not merely somewhere under the agent's config dir. That
matters — the config dir also holds the agent's transcripts, settings and plugin
cache, and a surface that says "memory" must not become a reader for those. The
alternative, re-running the scan and matching against its results, costs seconds
per request to answer a question the layout already answers.

Filesystem access goes through ``NativeMemoryScanPort`` (a Protocol this module
owns); the concrete adapters live in
``infrastructure/agent/native_memory_store.py`` and
``native_memory_files.py`` (Contract 2b: application defines the port,
infrastructure implements it).
"""

from __future__ import annotations

import asyncio
import functools
import pathlib
from typing import Protocol

from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.native_memory import (
    CodexGlobalLayout,
    MemoryFileContent,
    MemoryFileNode,
    NativeMemoryStore,
    ScannedStore,
    is_native_memory_dir,
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

    def build_tree(
        self, store_dir: pathlib.Path, *, only: frozenset[str] | None = None
    ) -> MemoryFileNode:
        """Return *store_dir* as a recursive read-only tree, restricted to the
        root entries in *only* when the directory holds more than the store."""
        ...

    def read_file(self, store_dir: pathlib.Path, relpath: str) -> MemoryFileContent:
        """Read one file under *store_dir* (capped, containment-checked)."""
        ...


# Structural type for the agent-lookup dependency — avoids a hard import of
# AgentService (and keeps this service unit-testable with a fake).
class _AgentLookup(Protocol):
    async def get(self, uid: str) -> Resource: ...


class AgentNativeMemoryService:
    def __init__(
        self,
        *,
        agent_service: _AgentLookup,
        scanner: NativeMemoryScanPort,
    ) -> None:
        self._agents = agent_service
        self._scanner = scanner

    async def list_stores(self, uid: str) -> list[NativeMemoryStore]:
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        cfg = AgentConfig.model_validate((await self._agents.get(uid)).config)
        layout = native_memory_layout_for(cfg.type)
        if layout is None:
            return []
        config_dir = cfg.resolved_config_dir()
        # The scan walks the agent's whole projects tree and, to recover a real
        # project path, reads sibling transcripts — seconds of blocking I/O on a
        # machine with many projects. The daemon serves the MCP gateway from this
        # same loop, so it runs off it.
        if isinstance(layout, CodexGlobalLayout):
            # Codex: one global task-grouped document, one row per routed cwd.
            scans = await asyncio.to_thread(
                self._scanner.scan_codex_global,
                config_dir / layout.memory_subdir,
                layout.index_file,
            )
        else:
            # Claude Code: one row per project that has a memory/ dir.
            scans = await asyncio.to_thread(
                self._scanner.scan,
                config_dir / layout.projects_subdir,
                layout.memory_subdir,
            )
        result = [self._to_store(scan) for scan in scans]
        return sorted(result, key=lambda s: (-s.item_count, s.project_label))

    async def read_tree(self, uid: str, memory_dir: str) -> MemoryFileNode:
        """The store at *memory_dir*, as a file tree.

        Raises ``ResourceNotFound`` when no such agent is registered and
        ``ValueError`` when *memory_dir* is not one of this agent's native
        memory stores — a client may only browse a directory the scan itself
        would have listed.
        """
        store_dir, only = await self._checked_store_dir(uid, memory_dir)
        return await asyncio.to_thread(
            functools.partial(self._scanner.build_tree, store_dir, only=only)
        )

    async def read_file(self, uid: str, memory_dir: str, relpath: str) -> MemoryFileContent:
        """One file inside the store at *memory_dir*.

        Raises as :meth:`read_tree` does, plus ``ValueError`` when *relpath*
        escapes the store and ``FileNotFoundError`` when nothing is there.
        """
        store_dir, _only = await self._checked_store_dir(uid, memory_dir)
        return await asyncio.to_thread(self._scanner.read_file, store_dir, relpath)

    async def _checked_store_dir(
        self, uid: str, memory_dir: str
    ) -> tuple[pathlib.Path, frozenset[str] | None]:
        """Resolve *memory_dir*, prove it is one of this agent's stores, and say
        which of its entries the store actually consists of.

        Resolution comes first so that a symlink pointing out of the config dir
        is judged by where it lands, not by how it is spelled.

        The second half of the answer exists because a store directory is not
        always the store. Codex's memory is one ``MEMORY.md`` inside
        ``~/.codex/memories``, and that directory also holds its automations,
        extensions, skills and a git checkout — so browsing the directory would
        put a pile of things that are not memory on a page that claims to show
        memory. A per-project store has no such problem, and gets ``None``.
        """
        # Raises ResourceNotFound (→ 404) when the agent doesn't exist.
        cfg = AgentConfig.model_validate((await self._agents.get(uid)).config)
        layout = native_memory_layout_for(cfg.type)
        candidate = pathlib.Path(memory_dir).resolve()
        if not is_native_memory_dir(layout, cfg.resolved_config_dir().resolve(), candidate):
            raise ValueError(f"not a native memory store of this agent: {memory_dir!r}")
        only = frozenset({layout.index_file}) if isinstance(layout, CodexGlobalLayout) else None
        return candidate, only

    @staticmethod
    def _to_store(scan: ScannedStore) -> NativeMemoryStore:
        # The real project path from the session transcript is authoritative when
        # present (the slug encoding is lossy: a hyphenated segment or any other
        # non-alphanumeric character in the home dir collapses to "-" and cannot be
        # told apart from a separator by string inspection alone). Only when no
        # transcript recorded a cwd do we fall back to the FS-aware slug decode,
        # which walks the real filesystem to disambiguate.
        if scan.project_path:
            path: str | None = scan.project_path
            label = pathlib.PurePath(scan.project_path).name or scan.project_path
        else:
            label, path = resolve_project_slug(scan.slug, _list_dirs)
        return NativeMemoryStore(
            project_label=label,
            project_path=path,
            slug=scan.slug,
            memory_dir=scan.memory_dir,
            item_count=scan.item_count,
        )


def _list_dirs(path: str) -> list[str]:
    """Real subdirectory names of ``path``, or ``[]`` if it cannot be listed.

    The FS adapter ``resolve_project_slug`` needs; kept here (rather than
    imported from infrastructure, which this layer may not import per
    Contract 2b) since it is a two-line ``pathlib`` wrapper, not logic worth
    routing through a port.
    """
    try:
        return [entry.name for entry in pathlib.Path(path).iterdir() if entry.is_dir()]
    except OSError:
        return []
