"""FileNativeMemoryScanner — filesystem adapter for native per-project memory.

Implements
``coffer.application.agent.native_memory_service.NativeMemoryScanPort``.
Read-only: it enumerates ``<projects_root>/<slug>/<memory_subdir>`` directories
and counts the memory entries inside each, never writing anything.
"""

from __future__ import annotations

import pathlib

from coffer.domain.agent.native_memory import ScannedStore
from coffer.infrastructure.agent.native_memory_import import (
    inline_memory_file,
    resolve_project_path,
)


class FileNativeMemoryScanner:
    """Scans an agent's projects root for per-project memory directories."""

    def scan(self, projects_root: pathlib.Path, memory_subdir: str) -> list[ScannedStore]:
        """Return a :class:`ScannedStore` per project that has a
        ``<slug>/<memory_subdir>/`` directory.

        ``item_count`` is the number of ``*.md`` fact files in that memory dir
        excluding the ``MEMORY.md`` index — or ``1`` when there are no fact files
        but ``MEMORY.md`` holds inline content (see :func:`inline_memory_file`),
        since that inline doc is itself the one importable entry.
        ``project_path`` is the real project
        directory, recovered via :func:`resolve_project_path` (the slug encoding
        is lossy, so the path cannot be decoded reliably — it is read from a
        sibling session transcript's ``cwd`` when the decoded slug is not a real
        dir), or ``None`` when it cannot be resolved. Returns ``[]`` when
        ``projects_root`` is not a directory. Non-directory entries under the
        root are skipped. Order is unspecified (the application sorts).
        """
        if not projects_root.is_dir():
            return []
        out: list[ScannedStore] = []
        for project_dir in projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            memory_dir = project_dir / memory_subdir
            if not memory_dir.is_dir():
                continue
            facts = sum(1 for f in memory_dir.glob("*.md") if f.is_file() and f.name != "MEMORY.md")
            # No separate fact files but inline content in MEMORY.md still counts
            # as one entry (it is what gets imported); see `inline_memory_file`.
            count = facts if facts else (1 if inline_memory_file(memory_dir) is not None else 0)
            out.append(
                ScannedStore(
                    slug=project_dir.name,
                    memory_dir=str(memory_dir),
                    item_count=count,
                    project_path=resolve_project_path(memory_dir),
                )
            )
        return out
