"""Infra reader for Codex's global task-grouped memory (``memories/MEMORY.md``).

The read-side counterpart to ``native_memory_store.py`` / ``native_memory_import.py``
for Codex's *global* store. Codex keeps one document routing many projects via
per-Task-Group ``cwd`` annotations (parsed by ``domain.agent.codex_memory``); this
module turns it into one :class:`ScannedStore` per distinct cwd (for the listing)
and reads the Task-Group blocks routed to a given project path (for import).

Listing and import are kept symmetric: a store's ``item_count`` equals the number
of facts :func:`read_codex_facts` returns for that store's project path.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.agent.codex_memory import CodexMemoryEntry, parse_codex_memory
from coffer.domain.agent.native_memory import ParsedNativeFact, ScannedStore


def _read_entries(memories_dir: pathlib.Path, index_file: str) -> list[CodexMemoryEntry]:
    """Parse the global memory document, or ``[]`` if it is absent/unreadable."""
    index = memories_dir / index_file
    try:
        text = index.read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_codex_memory(text)


def codex_stores(memories_dir: pathlib.Path, index_file: str) -> list[ScannedStore]:
    """One :class:`ScannedStore` per distinct routed cwd in the global document.

    ``item_count`` is the number of Task Groups routed to that cwd; ``memory_dir``
    is the shared global memories dir for every row; ``project_path`` is the cwd
    with ``~`` expanded (the slug keeps the raw cwd). A group routed to several
    cwds contributes to each. Returns ``[]`` when the document is absent.
    """
    counts: dict[str, int] = {}
    for entry in _read_entries(memories_dir, index_file):
        for cwd in entry.cwds:
            counts[cwd] = counts.get(cwd, 0) + 1
    return [
        ScannedStore(
            slug=cwd,
            memory_dir=str(memories_dir),
            item_count=count,
            project_path=os.path.expanduser(cwd),
        )
        for cwd, count in counts.items()
    ]


def read_codex_facts(
    memories_dir: pathlib.Path, project_path: str, index_file: str
) -> list[ParsedNativeFact]:
    """Task-Group blocks routed to ``project_path``, as importable facts.

    A group matches when any of its (``~``-expanded) cwds equals ``project_path``.
    Each matching group becomes one fact: ``name`` is the group title, ``body`` is
    the verbatim block. Returns ``[]`` when nothing routes to ``project_path``.
    """
    facts: list[ParsedNativeFact] = []
    for entry in _read_entries(memories_dir, index_file):
        if any(os.path.expanduser(cwd) == project_path for cwd in entry.cwds):
            facts.append(
                ParsedNativeFact(
                    name=entry.title or "Codex memory",
                    description="",
                    body=entry.body,
                    origin_session_id=None,
                )
            )
    return facts


__all__ = ["codex_stores", "read_codex_facts"]
