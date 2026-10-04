"""The table chat is stored in: ``conversations`` — the index of the channel
conversations (the text of a conversation lives in the agent's own session).

Beside the repo rather than inside it, because a table's shape is read far
more often than the queries over it — a migration and a projection all want the
columns and none of them wants the repo.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class ConversationModel(Base):
    """Row in the ``conversations`` table."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # No column default. It used to be ``"builtin"``, an agent that has since
    # been withdrawn and is refused at channel create/edit — so the default
    # could only ever mint a row no turn can route. Every writer passes the
    # key explicitly; an absent one is a programming error, not a fallback.
    agent_key: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    # Provider-owned per-conversation state (cwd + upstream session id + model),
    # stored as the JSON of an ``AgentConfig``; NULL = none. See
    # ConversationRepo.*_agent_config.
    agent_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # Optional channel binding (return address, spec channels) for a conversation the
    # owner also drives from an IM channel; "has a binding" iff channel_uid set.
    #
    # The channel resource's uid, not its name. This is a cross-resource
    # reference and the name is a mutable label (ADR
    # identity-is-the-uid-inside-the-file) — storing the label would leave
    # every row written before a rename pointing at a channel that no longer
    # answers to it. The name the user and the agent read is resolved from this
    # uid at read time.
    channel_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    peer_chat_id: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (Index("idx_conversations_updated", "updated_at"),)
