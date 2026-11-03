"""Infra reader for Codex's global task-grouped memory (``memories/MEMORY.md``)
and its v2 memory (``memories_v2/memory_summary.md``).

The Codex counterpart to ``native_memory_store.py``. Codex keeps one document
routing many projects via per-Task-Group ``cwd`` annotations (parsed by
``domain.agent.codex_memory``); this module turns it into one
:class:`ScannedStore` per distinct cwd for the read-only listing.

Read-only: nothing here writes the agent's document.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.agent.codex_memory import (
    CodexMemoryEntry,
    parse_codex_memory,
    parse_codex_v2_topics,
)
from coffer.domain.agent.native_memory import ScannedStore
from coffer.infrastructure.agent_files.codex_rollout_summaries import rollout_cwd

_V2_INDEX = "memory_summary.md"


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
    if index_file == _V2_INDEX:
        # v2: one row per cwd its topics' rollout summaries name, a topic each.
        for cwd in _v2_cwds(memories_dir):
            counts[cwd] = counts.get(cwd, 0) + 1
    for entry in _read_entries(memories_dir, index_file) if index_file != _V2_INDEX else []:
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


def _v2_cwds(folder: pathlib.Path) -> list[str]:
    try:
        text = (folder / _V2_INDEX).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out = []
    for topic in parse_codex_v2_topics(text):
        cwd = rollout_cwd(folder, topic.rollout_file)
        if cwd:
            out.append(cwd)
    return out


__all__ = ["codex_stores"]
