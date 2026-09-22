"""The two tables chat is stored in: ``conversations`` and ``chat_messages``.

Beside the repos rather than inside them, because a table's shape is read far
more often than the queries over it — a migration, a retention policy and a
projection all want the columns and none of them wants the repo — and because
keeping both here is what lets ``persistence.py`` be about the reads and
writes alone.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Optional channel binding (return address, spec channels) for a conversation the
    # owner also drives from an IM channel; "has a binding" iff channel_uid set.
    #
    # The channel resource's uid, not its name. This is a cross-resource
    # reference and the name is a mutable label (ADR
    # resource-identity-is-an-immutable-uid) — storing the label would leave
    # every row written before a rename pointing at a channel that no longer
    # answers to it. The name the user and the agent read is resolved from this
    # uid at read time.
    channel_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    peer_chat_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Whose conversation this is. NULL is the developer's own — the only kind
    # the chat list shows — and a name is the surface that owns it. Chat needs
    # no idea what any such name means: it lists the unowned ones, and
    # everything else belongs to whoever put a name here.
    owner: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("idx_conversations_updated", "updated_at"),
        Index("idx_conversations_archived", "archived_at"),
        Index("idx_conversations_owner", "owner"),
    )


class MessageModel(Base):
    """Row in the ``chat_messages`` table."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of content blocks
    status: Mapped[str] = mapped_column(String, nullable=False, default="complete")
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_chat_messages_conv_seq"),
        Index("idx_chat_messages_conv", "conversation_id", "seq"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
