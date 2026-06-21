# backend/coffer/domain/memory/journal.py
"""``JournalEntry`` value object — one episodic event in the journal lane.

Files-as-truth: the entry on disk (a timestamped block in a time-partitioned
``journal/<YYYY-MM>.md``) is canonical; this is the in-memory view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = ["JournalEntry"]


@dataclass(frozen=True)
class JournalEntry:
    timestamp: datetime
    body: str
