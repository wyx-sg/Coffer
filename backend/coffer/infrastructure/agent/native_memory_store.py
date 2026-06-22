"""FileNativeMemoryScanner — filesystem adapter for native per-project memory.

Implements
``coffer.application.agent.native_memory_service.NativeMemoryScanPort``.
Read-only: it enumerates ``<projects_root>/<slug>/<memory_subdir>`` directories
and counts the fact files inside each, never writing anything.
"""

from __future__ import annotations

import pathlib

from coffer.domain.agent.native_memory import ScannedStore
from coffer.infrastructure.agent.native_memory_import import resolve_project_path


class FileNativeMemoryScanner:
    """Scans an agent's projects root for per-project memory directories."""

    def scan(self, projects_root: pathlib.Path, memory_subdir: str) -> list[ScannedStore]:
        """Return a :class:`ScannedStore` per project that has a
        ``<slug>/<memory_subdir>/`` directory.

        ``item_count`` is the number of ``*.md`` files in that memory dir
        excluding the ``MEMORY.md`` index. ``project_path`` is the real project
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
            count = sum(1 for f in memory_dir.glob("*.md") if f.is_file() and f.name != "MEMORY.md")
            out.append(
                ScannedStore(
                    slug=project_dir.name,
                    memory_dir=str(memory_dir),
                    item_count=count,
                    project_path=resolve_project_path(memory_dir),
                )
            )
        return out
