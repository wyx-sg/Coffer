"""Conversation domain entity — a persisted chat thread."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Conversation:
    """A persisted chat thread.

    Not a Resource — stored in the dedicated ``conversations`` SQLite table.
    ``agent_key`` identifies which agent the thread talks to; v1 always ``"builtin"``.
    ``archived_at`` is ``None`` for an active thread, or the instant it was
    archived; archived threads are hidden from the default list but restorable.

    An optional **channel binding** (``channel_uid`` + ``peer_chat_id``) is the
    return address for relaying the agent's output back to an IM channel
    (spec channels). A conversation "has a channel binding" iff ``channel_uid`` is set.
    Under the single-owner premise the IM peer is always the owner, so there is no
    separate peer identity to display.

    ``channel_uid`` holds the channel resource's **uid**, not its name (ADR
    resource-identity-is-an-immutable-uid). It is a stored cross-reference that
    has to survive the user renaming the channel, and the name cannot do that:
    a row written before the rename would afterwards name a channel that no
    longer exists, and — once the old name is free again — could come to name a
    different one. Everywhere a human or a model reads the channel, the label
    is resolved from the uid at that moment; nothing keeps a second copy of it.

    ``owner`` says whose conversation this is. ``None`` is the developer's own,
    which is what the chat list shows; a name is the surface that owns it — a
    workflow task's conversation belongs to its run (spec workflow, FR-030) and
    is not one of the developer's threads, however ordinary its transcript is.
    """

    id: str
    agent_key: str
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    channel_uid: str | None = None
    owner: str | None = None
    peer_chat_id: str | None = None
