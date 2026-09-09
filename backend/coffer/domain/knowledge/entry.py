"""``KnowledgeEntry`` value object — the in-memory view of one per-entry
markdown file (YAML frontmatter + body). The file on disk is the source of
truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

#: Who wrote an entry.
Actor = Literal["agent", "user"]


@dataclass(frozen=True)
class KnowledgeEntry:
    """One knowledge entry = one markdown file = one ``documents`` row."""

    id: str
    title: str
    description: str
    body: str
    actor: Actor
    created_at: datetime
    updated_at: datetime
    origin_session_id: str | None = None
