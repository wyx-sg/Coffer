"""FileNativeMemoryScanner — filesystem adapter for native per-project memory.

Implements
``coffer.application.agent.native_memory_service.NativeMemoryScanPort``.
Read-only: it enumerates ``<projects_root>/<slug>/<memory_subdir>`` directories
and counts the memory entries inside each, and — for one store the caller has
already proved is the agent's — hands back its tree and its files (delegated to
``native_memory_files``). It never writes anything.
"""

from __future__ import annotations

import os
import pathlib
import threading

from coffer.domain.agent.native_memory import (
    MemoryFileContent,
    MemoryFileNode,
    ScannedStore,
    encode_slug,
)
from coffer.infrastructure.agent import native_memory_files
from coffer.infrastructure.agent.codex_memory_store import codex_stores
from coffer.infrastructure.agent_files.claude_code_transcripts import cwd_from_transcripts

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


def _fact_count(memory_dir: pathlib.Path) -> int:
    """``*.md`` files other than the index, from a single directory scan."""
    try:
        with os.scandir(memory_dir) as it:
            return sum(
                1 for e in it if e.name.endswith(".md") and e.name != _INDEX_FILE and e.is_file()
            )
    except OSError:
        return 0


def _resolve_project_path(memory_dir: pathlib.Path) -> str | None:
    """Recover the REAL absolute project path that ``memory_dir`` belongs to.

    Reads the first sibling ``*.jsonl`` session transcript's recorded ``cwd``
    (:func:`cwd_from_transcripts`) — Claude Code's own record of where the
    session ran, and strictly more reliable than decoding the slug, since
    the slug's ``/``-and-everything-else-to-``-`` encoding is ambiguous
    exactly where a real path segment contains a character other than a
    letter or digit. Returns ``None`` when no transcript records one; a mere
    best-effort *guess* from the slug
    (``coffer.domain.agent.native_memory.resolve_project_slug``) is left to
    ``AgentNativeMemoryService._to_store``, the one place in this feature a
    guess belongs.
    """
    return cwd_from_transcripts(memory_dir.parent, encode_slug)


#: How many projects' recovered paths one scanner remembers.
_PATH_MEMO_MAX = 2048

_Signature = int


def _transcript_signature(project_dir: pathlib.Path) -> _Signature | None:
    """The project directory's mtime — it moves whenever a session transcript is
    created or removed, and costs one stat where listing the transcripts costs a
    directory scan. ``None`` when it cannot be read (nothing is then remembered)."""
    try:
        return project_dir.stat().st_mtime_ns
    except OSError:
        return None


def _remember[V](memo: dict[pathlib.Path, V], key: pathlib.Path, value: V) -> None:
    """Insert into a bounded memo, dropping the oldest entry when full."""
    if key not in memo and len(memo) >= _PATH_MEMO_MAX:
        memo.pop(next(iter(memo)))
    memo[key] = value


class FileNativeMemoryScanner:
    """Scans an agent's native memory: Claude Code's per-project dirs and Codex's
    single global task-grouped store.

    Recovering a project's real path reads its transcripts, so the answer is
    remembered per project directory (bounded, in memory only). A recovered path
    is kept as is: the slug encodes the path, so the same directory cannot come
    to name another one. "No transcript says" is kept only against the project
    directory's mtime, so a new or removed transcript triggers a fresh read (a
    transcript that merely grows into a matching ``cwd`` is picked up with the
    next one; until then the caller's slug-decode guess stands).
    """

    def __init__(self) -> None:
        self._found: dict[pathlib.Path, str] = {}
        self._missing: dict[pathlib.Path, _Signature] = {}
        # ``scan`` runs on worker threads; two requests may overlap.
        self._lock = threading.Lock()

    def _project_path(self, memory_dir: pathlib.Path) -> str | None:
        project_dir = memory_dir.parent
        with self._lock:
            known = self._found.get(project_dir)
        if known is not None:
            return known
        sig = _transcript_signature(project_dir)
        with self._lock:
            if sig is not None and self._missing.get(project_dir) == sig:
                return None
        found = _resolve_project_path(memory_dir)
        with self._lock:
            if found is not None:
                self._missing.pop(project_dir, None)
                _remember(self._found, project_dir, found)
            elif sig is not None:
                _remember(self._missing, project_dir, sig)
        return found

    def scan(self, projects_root: pathlib.Path, memory_subdir: str) -> list[ScannedStore]:
        """Return a :class:`ScannedStore` per project that has a
        ``<slug>/<memory_subdir>/`` directory.

        ``item_count`` is the number of ``*.md`` fact files in that memory dir
        excluding the ``MEMORY.md`` index — or ``1`` when there are no fact files
        but ``MEMORY.md`` holds inline content (see :func:`_inline_memory_file`),
        since that inline doc is itself the store's one entry. ``project_path``
        is the real project directory, recovered via :func:`_resolve_project_path`
        from a sibling session transcript's ``cwd`` (the slug encoding is too
        lossy to decode reliably on its own — see that function), or ``None``
        when no transcript records one. Returns ``[]`` when ``projects_root``
        is not a directory. Non-directory entries under the root are skipped.
        Order is unspecified (the application sorts).
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
            facts = _fact_count(memory_dir)
            # No separate fact files but inline content in MEMORY.md still counts
            # as one entry; see `_inline_memory_file`.
            count = facts if facts else (1 if _inline_memory_file(memory_dir) is not None else 0)
            out.append(
                ScannedStore(
                    slug=project_dir.name,
                    memory_dir=str(memory_dir),
                    item_count=count,
                    project_path=self._project_path(memory_dir),
                )
            )
        return out

    def scan_codex_global(self, memories_dir: pathlib.Path, index_file: str) -> list[ScannedStore]:
        """Return a :class:`ScannedStore` per distinct routed cwd in Codex's
        single global task-grouped store (``memories_dir/<index_file>``)."""
        return codex_stores(memories_dir, index_file)

    def build_tree(
        self, store_dir: pathlib.Path, *, only: frozenset[str] | None = None
    ) -> MemoryFileNode:
        """One store's directory as a read-only tree (see ``native_memory_files``).

        The caller has already established that ``store_dir`` is one of this
        agent's stores; this adapter's only remaining job is the walk — and,
        for a layout whose directory holds more than the store, keeping to the
        entries ``only`` names.
        """
        return native_memory_files.build_tree(store_dir, only=only)

    def read_file(self, store_dir: pathlib.Path, relpath: str) -> MemoryFileContent:
        """One file inside a store, capped and containment-checked."""
        return native_memory_files.read_file(store_dir, relpath)
