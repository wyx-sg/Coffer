"""Value objects for the cross-agent transcript history (ADR-022).

These are the read-model the Vault Console renders: a session reference, a
search hit (a scrubbed snippet plus where it came from), and a browsed session
(its scrubbed natural-language turns). None of these are persisted — the source
of truth stays the agent's own ``.jsonl`` on disk; the SQLite index is derived.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HistorySessionRef:
    """A transcript session as listed/searched — never its raw content."""

    agent_type: str
    session_id: str
    project_path: str | None
    started_at: datetime | None
    title: str
    message_count: int


@dataclass(frozen=True)
class HistorySearchHit:
    """One keyword/vector hit: a scrubbed snippet and its provenance."""

    agent_type: str
    session_id: str
    project_path: str | None
    started_at: datetime | None
    title: str
    snippet: str
    score: float


@dataclass(frozen=True)
class HistoryTurn:
    """One scrubbed natural-language turn (role + text, no tool payloads)."""

    role: str
    text: str


@dataclass(frozen=True)
class HistorySessionDetail:
    """A browsed session: its reference plus its scrubbed turns (read-only)."""

    ref: HistorySessionRef
    turns: tuple[HistoryTurn, ...]


@dataclass(frozen=True)
class RebuildStats:
    """Outcome of a (re)index run over the on-disk transcripts."""

    indexed: int
    unchanged: int
    removed: int
