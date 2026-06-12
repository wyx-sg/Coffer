"""Retrieval value objects shared by KB and memory (not persisted)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

#: The three retrieval modes the substrate supports.
RetrievalMode = Literal["grep", "keyword", "vector"]
RETRIEVAL_MODES: tuple[RetrievalMode, ...] = ("grep", "keyword", "vector")


@dataclass(frozen=True)
class StoreRef:
    """Identifies one logical store (one KB or one memory scope) in the unified
    table. ``kind`` discriminates the face; ``resource_name`` names the store.

    ``project_id`` is the memory scope key (the global sentinel for KB and for
    global memory). ``docs_dir`` is the on-disk directory holding the Markdown
    files for grep and lazy-reindex scans.
    """

    kind: str
    resource_name: str
    project_id: str
    docs_dir: str


@dataclass(frozen=True)
class Passage:
    """A keyword/vector search hit (KB face and memory recall)."""

    document_id: str
    title: str
    text: str
    score: float
    position: int


@dataclass(frozen=True)
class GrepHit:
    """A ripgrep file/line match (no index involved)."""

    path: str
    line_number: int
    line: str


@dataclass(frozen=True)
class GrepResult:
    """The outcome of a grep.

    ``truncated`` is True when matches beyond ``max_matches`` exist or the
    wall-clock timeout cut the scan short — never a count heuristic.
    """

    hits: Sequence[GrepHit] = field(default_factory=tuple)
    truncated: bool = False


@dataclass(frozen=True)
class MemoryHit:
    """A memory recall result (the memory face's view of a ``Passage``)."""

    id: str
    text: str
    score: float
    source: str
    time: datetime


@dataclass(frozen=True)
class SearchResult:
    """The outcome of a search.

    ``fallback`` is set to ``"keyword"`` when a requested ``vector`` search
    degraded because no embedding provider was configured / available — the
    call never errors, it flags the fallback instead.
    """

    mode: RetrievalMode
    passages: Sequence[Passage] = field(default_factory=tuple)
    fallback: RetrievalMode | None = None
