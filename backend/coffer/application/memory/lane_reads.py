"""Read-only lane projections for the four-lane memory UI (spec 007 Slice 7).

Pure file reads over a store's ``journal/`` / ``handoff/`` lanes and the
store-root ``consolidation-log.md`` — no LLM, no index. The HTTP surface maps
these value objects straight onto its wire schemas; the ``MemoryService``
methods are thin ``asyncio.to_thread`` wrappers around the free functions here.

Empty lane → empty list; absent changelog → ``text=None``. Never an error: an
empty store is a 200 with empty content, mirroring ``get_rules``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coffer.domain.memory.scope import ResolvedScope
from coffer.infrastructure.knowledge.paths import (
    consolidation_log_path,
    handoff_dir,
    journal_dir,
)
from coffer.infrastructure.memory.handoff_files import read_handoff

ResolveStoreFn = Callable[[str], Awaitable[ResolvedScope]]


@dataclass(frozen=True)
class JournalFile:
    """One time-partitioned ``journal/<period>.md`` file (raw markdown body)."""

    period: str
    text: str
    path: str
    folder_path: str


@dataclass(frozen=True)
class HandoffScene:
    """One per-branch ``handoff/<slug>.md`` scene (frontmatter + body)."""

    branch: str
    text: str
    updated_at: datetime
    path: str
    folder_path: str


@dataclass(frozen=True)
class ConsolidationLog:
    """The store-root ``consolidation-log.md`` changelog; ``text=None`` when absent."""

    text: str | None
    path: str
    folder_path: str


def read_journal_files(store_dir: Path) -> list[JournalFile]:
    """List ``journal/<period>.md`` files, NEWEST period first (empty → ``[]``)."""
    d = journal_dir(store_dir)
    if not d.exists():
        return []
    out: list[JournalFile] = []
    for path in sorted(d.glob("*.md"), key=lambda p: p.stem, reverse=True):
        out.append(
            JournalFile(
                period=path.stem,
                text=path.read_text(encoding="utf-8").strip("\n"),
                path=str(path),
                folder_path=str(path.parent),
            )
        )
    return out


def read_handoff_scenes(store_dir: Path) -> list[HandoffScene]:
    """List ``handoff/<slug>.md`` scenes, one per branch (empty → ``[]``)."""
    d = handoff_dir(store_dir)
    if not d.exists():
        return []
    out: list[HandoffScene] = []
    for path in sorted(d.glob("*.md")):
        handoff = read_handoff(path)
        if handoff is None:
            continue
        out.append(
            HandoffScene(
                branch=handoff.branch,
                text=handoff.body,
                updated_at=handoff.updated_at,
                path=str(path),
                folder_path=str(path.parent),
            )
        )
    return out


def read_consolidation_log(store_dir: Path) -> ConsolidationLog:
    """Read the store-root ``consolidation-log.md`` (``text=None`` when absent)."""
    path = consolidation_log_path(store_dir)
    try:
        text: str | None = path.read_text(encoding="utf-8").strip("\n") or None
    except OSError:
        text = None
    return ConsolidationLog(text=text, path=str(path), folder_path=str(path.parent))


async def journal_for_store(store_name: str, resolved_store: ResolveStoreFn) -> list[JournalFile]:
    sd = (await resolved_store(store_name)).store_dir
    return await asyncio.to_thread(read_journal_files, sd)


async def handoff_for_store(store_name: str, resolved_store: ResolveStoreFn) -> list[HandoffScene]:
    sd = (await resolved_store(store_name)).store_dir
    return await asyncio.to_thread(read_handoff_scenes, sd)


async def consolidation_log_for_store(
    store_name: str, resolved_store: ResolveStoreFn
) -> ConsolidationLog:
    sd = (await resolved_store(store_name)).store_dir
    return await asyncio.to_thread(read_consolidation_log, sd)
