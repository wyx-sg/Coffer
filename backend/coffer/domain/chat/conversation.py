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

    An optional **channel binding** (``channel_name`` + ``peer_chat_id``) is the
    return address for relaying the agent's output back to an IM channel
    (ADR-031). A conversation "has a channel binding" iff ``channel_name`` is set.
    Under the single-owner premise the IM peer is always the owner, so there is no
    separate peer identity to display.
    """

    id: str
    agent_key: str
    title: str
    model_id: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    channel_name: str | None = None
    peer_chat_id: str | None = None
