"""FileNativeMemoryScanner — filesystem adapter for native per-project memory.

Implements
``coffer.application.agent.native_memory_service.NativeMemoryScanPort``.
Read-only: it enumerates ``<projects_root>/<slug>/<memory_subdir>`` directories
and counts the memory entries inside each, never writing anything.
"""

from __future__ import annotations

import json
import pathlib

from coffer.domain.agent.native_memory import ScannedStore, decode_project_slug
from coffer.infrastructure.agent.codex_memory_store import codex_stores

_INDEX_FILE = "MEMORY.md"


def _inline_memory_file(memory_dir: pathlib.Path) -> pathlib.Path | None:
    """Return the ``MEMORY.md`` path iff it is the store's *only* memory content.

    The standard Claude Code layout is one fact per ``*.md`` file with
    ``MEMORY.md`` as a pure index — there, ``MEMORY.md`` is not a fact and is
    excluded from the count. But some projects keep everything *inline* in
    ``MEMORY.md`` with no separate fact files (an older / hand-written hub doc).
    In that case ``MEMORY.md`` *is* the memory: return it so the store counts as
    holding one entry. Returns ``None`` when fact files exist (``MEMORY.md`` is
    then an index) or ``MEMORY.md`` is absent / blank.
    """
    if not memory_dir.is_dir():
        return None
    if any(f.is_file() and f.name != _INDEX_FILE for f in memory_dir.glob("*.md")):
        return None
    index = memory_dir / _INDEX_FILE
    try:
        has_content = index.is_file() and bool(index.read_text(encoding="utf-8").strip())
    except OSError:
        return None
    return index if has_content else None


def _cwd_from_transcripts(project_dir: pathlib.Path) -> str | None:
    """First ``"cwd"`` string found in the first readable sibling ``*.jsonl``."""
    if not project_dir.is_dir():
        return None
    for jsonl in sorted(project_dir.glob("*.jsonl")):
        try:
            text = jsonl.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                cwd = record.get("cwd")
                if isinstance(cwd, str):
                    return cwd
        # First readable transcript only (per the contract): stop after it.
        return None
    return None


def _resolve_project_path(memory_dir: pathlib.Path) -> str | None:
    """Recover the REAL absolute project path that ``memory_dir`` belongs to.

    Two-step resolution:
      1. Decode the parent dir name (the slug). If the decoded path is an
         existing directory, use it.
      2. Else scan the first readable sibling ``*.jsonl`` transcript (one JSON
         object per line; bad lines skipped) for a record carrying a string
         ``"cwd"`` and use that.
    Returns ``None`` when neither resolves.
    """
    project_dir = memory_dir.parent
    _, decoded = decode_project_slug(project_dir.name)
    if decoded is not None and pathlib.Path(decoded).is_dir():
        return decoded
    return _cwd_from_transcripts(project_dir)


class FileNativeMemoryScanner:
    """Scans an agent's native memory: Claude Code's per-project dirs and Codex's
    single global task-grouped store."""

    def scan(self, projects_root: pathlib.Path, memory_subdir: str) -> list[ScannedStore]:
        """Return a :class:`ScannedStore` per project that has a
        ``<slug>/<memory_subdir>/`` directory.

        ``item_count`` is the number of ``*.md`` fact files in that memory dir
        excluding the ``MEMORY.md`` index — or ``1`` when there are no fact files
        but ``MEMORY.md`` holds inline content (see :func:`_inline_memory_file`),
        since that inline doc is itself the store's one entry. ``project_path``
        is the real project directory, recovered via :func:`_resolve_project_path`
        (the slug encoding is lossy, so the path cannot be decoded reliably — it
        is read from a sibling session transcript's ``cwd`` when the decoded slug
        is not a real dir), or ``None`` when it cannot be resolved. Returns ``[]``
        when ``projects_root`` is not a directory. Non-directory entries under the
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
            facts = sum(1 for f in memory_dir.glob("*.md") if f.is_file() and f.name != _INDEX_FILE)
            # No separate fact files but inline content in MEMORY.md still counts
            # as one entry; see `_inline_memory_file`.
            count = facts if facts else (1 if _inline_memory_file(memory_dir) is not None else 0)
            out.append(
                ScannedStore(
                    slug=project_dir.name,
                    memory_dir=str(memory_dir),
                    item_count=count,
                    project_path=_resolve_project_path(memory_dir),
                )
            )
        return out

    def scan_codex_global(self, memories_dir: pathlib.Path, index_file: str) -> list[ScannedStore]:
        """Return a :class:`ScannedStore` per distinct routed cwd in Codex's
        single global task-grouped store (``memories_dir/<index_file>``)."""
        return codex_stores(memories_dir, index_file)
