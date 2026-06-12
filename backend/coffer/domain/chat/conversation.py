"""Conversation domain entity — a persisted chat thread."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Conversation:
    """A persisted chat thread.

    Not a Resource — stored in the dedicated ``conversations`` SQLite table.
    ``agent_key`` identifies which agent the thread talks to; v1 always ``"builtin"``.
    ``model_id`` is an optional override; ``None`` means use the default model.
    ``archived_at`` is ``None`` for an active thread, or the instant it was
    archived; archived threads are hidden from the default list but restorable.
    """

    id: str
    agent_key: str
    title: str
    model_id: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
