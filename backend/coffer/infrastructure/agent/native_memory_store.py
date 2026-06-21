"""FileNativeMemoryScanner — filesystem adapter for native per-project memory.

Implements
``coffer.application.agent.native_memory_service.NativeMemoryScanPort``.
Read-only: it enumerates ``<projects_root>/<slug>/<memory_subdir>`` directories
and counts the fact files inside each, never writing anything.
"""

from __future__ import annotations

import pathlib


class FileNativeMemoryScanner:
    """Scans an agent's projects root for per-project memory directories."""

    def scan(self, projects_root: pathlib.Path, memory_subdir: str) -> list[tuple[str, str, int]]:
        """Return ``(slug, memory_dir_abs, item_count)`` per project that has a
        ``<slug>/<memory_subdir>/`` directory.

        ``item_count`` is the number of ``*.md`` files in that memory dir
        excluding the ``MEMORY.md`` index. Returns ``[]`` when ``projects_root``
        is not a directory. Non-directory entries under the root are skipped.
        Order is unspecified (the application sorts).
        """
        if not projects_root.is_dir():
            return []
        out: list[tuple[str, str, int]] = []
        for project_dir in projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            memory_dir = project_dir / memory_subdir
            if not memory_dir.is_dir():
                continue
            count = sum(1 for f in memory_dir.glob("*.md") if f.is_file() and f.name != "MEMORY.md")
            out.append((project_dir.name, str(memory_dir), count))
        return out
