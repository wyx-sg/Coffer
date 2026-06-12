"""SQLAlchemy ORM models and repos for conversations + messages.

Tables: ``conversations``, ``chat_messages``.
Implements the ``ConversationRepo`` and ``MessageRepo`` Protocols defined in
``coffer.application.chat.service``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.message import (
    ContentBlock,
    Message,
    Role,
    block_from_dict,
    block_to_dict,
)
from coffer.domain.errors import ConversationNotFound
from coffer.infrastructure.persistence.base import Base

# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class ConversationModel(Base):
    """Row in the ``conversations`` table."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_key: Mapped[str] = mapped_column(String, nullable=False, default="builtin")
    title: Mapped[str] = mapped_column(String, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_conversations_updated", "updated_at"),
        Index("idx_conversations_archived", "archived_at"),
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


def _tz(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (UTC)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _encode_content(blocks: list[ContentBlock]) -> str:
    """Serialize content blocks to JSON text for DB storage."""
    return json.dumps([block_to_dict(b) for b in blocks])


def _decode_content(raw: str) -> list[ContentBlock]:
    """Deserialize JSON text from DB into a list of ContentBlock."""
    data: list[dict[str, Any]] = json.loads(raw)
    return [block_from_dict(d) for d in data]


# ---------------------------------------------------------------------------
# ConversationRepo
# ---------------------------------------------------------------------------


class ConversationRepo:
    """SQLAlchemy implementation of the ``ConversationRepo`` Protocol."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    def _to_domain(self, row: ConversationModel) -> Conversation:
        return Conversation(
            id=row.id,
            agent_key=row.agent_key,
            title=row.title,
            model_id=row.model_id,
            created_at=_tz(row.created_at),
            updated_at=_tz(row.updated_at),
            archived_at=_tz(row.archived_at) if row.archived_at else None,
        )

    async def create(self, conversation: Conversation) -> Conversation:
        async with self._sm() as session:
            row = ConversationModel(
                id=conversation.id,
                agent_key=conversation.agent_key,
                title=conversation.title,
                model_id=conversation.model_id,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row)

    async def get(self, conversation_id: str) -> Conversation | None:
        async with self._sm() as session:
            stmt = select(ConversationModel).where(ConversationModel.id == conversation_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def list(self, *, archived: bool = False) -> list[Conversation]:
        """Conversations newest first. ``archived=False`` (default) returns active
        threads only; ``archived=True`` returns the archived ones."""
        async with self._sm() as session:
            stmt = select(ConversationModel).order_by(ConversationModel.updated_at.desc())
            stmt = stmt.where(
                ConversationModel.archived_at.isnot(None)
                if archived
                else ConversationModel.archived_at.is_(None)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def rename(self, conversation_id: str, new_title: str) -> Conversation:
        async with self._sm() as session:
            stmt = (
                update(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .values(title=new_title)
                .returning(ConversationModel)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ConversationNotFound(conversation_id)
            await session.commit()
            return self._to_domain(row)

    async def touch(self, conversation_id: str, updated_at: datetime) -> None:
        """Bump ``updated_at`` for the given conversation."""
        async with self._sm() as session:
            stmt = (
                update(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .values(updated_at=updated_at)
            )
            await session.execute(stmt)
            await session.commit()

    async def set_model(self, conversation_id: str, model_id: str | None) -> Conversation:
        async with self._sm() as session:
            stmt = (
                update(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .values(model_id=model_id)
                .returning(ConversationModel)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ConversationNotFound(conversation_id)
            await session.commit()
            return self._to_domain(row)

    async def set_archived(
        self, conversation_id: str, archived_at: datetime | None
    ) -> Conversation:
        """Archive (``archived_at`` = a timestamp) or restore (``None``)."""
        async with self._sm() as session:
            stmt = (
                update(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .values(archived_at=archived_at)
                .returning(ConversationModel)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ConversationNotFound(conversation_id)
            await session.commit()
            return self._to_domain(row)

    async def delete(self, conversation_id: str) -> None:
        async with self._sm() as session:
            stmt = sa_delete(ConversationModel).where(ConversationModel.id == conversation_id)
            await session.execute(stmt)
            await session.commit()


# ---------------------------------------------------------------------------
# MessageRepo
# ---------------------------------------------------------------------------


class MessageRepo:
    """SQLAlchemy implementation of the ``MessageRepo`` Protocol."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    def _to_domain(self, row: MessageModel) -> Message:
        return Message(
            id=row.id,
            conversation_id=row.conversation_id,
            seq=row.seq,
            role=Role(row.role),
            content=_decode_content(row.content),
            status=row.status,  # type: ignore[arg-type]
            model_id=row.model_id,
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            created_at=_tz(row.created_at),
        )

    async def append(self, message: Message) -> Message:
        async with self._sm() as session:
            row = MessageModel(
                id=message.id,
                conversation_id=message.conversation_id,
                seq=message.seq,
                role=message.role,
                content=_encode_content(message.content),
                status=message.status,
                model_id=message.model_id,
                prompt_tokens=message.prompt_tokens,
                completion_tokens=message.completion_tokens,
                created_at=message.created_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_domain(row)

    async def finalize(
        self,
        message_id: str,
        *,
        content: list[ContentBlock],
        status: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        """Update an existing (streaming) message with its final content/status.

        Used to finalize the streaming placeholder written at turn start, so a
        completed turn occupies exactly one row.
        """
        async with self._sm() as session:
            stmt = (
                update(MessageModel)
                .where(MessageModel.id == message_id)
                .values(
                    content=_encode_content(content),
                    status=status,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def delete_message(self, message_id: str) -> None:
        """Delete a single message by id (used to discard a placeholder row)."""
        async with self._sm() as session:
            stmt = sa_delete(MessageModel).where(MessageModel.id == message_id)
            await session.execute(stmt)
            await session.commit()

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        """Return messages ordered by ``seq`` ascending."""
        async with self._sm() as session:
            stmt = (
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.seq.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def next_seq(self, conversation_id: str) -> int:
        """Return the next sequence number for the given conversation.

        Uses ``COALESCE(MAX(seq) + 1, 0)`` so the result is correct even
        when prior rows have been deleted and sequence numbers are non-contiguous.
        """
        async with self._sm() as session:
            stmt = select(func.coalesce(func.max(MessageModel.seq) + 1, 0)).where(
                MessageModel.conversation_id == conversation_id
            )
            return int((await session.execute(stmt)).scalar_one())

    async def delete_by_conversation(self, conversation_id: str) -> None:
        async with self._sm() as session:
            stmt = sa_delete(MessageModel).where(MessageModel.conversation_id == conversation_id)
            await session.execute(stmt)
            await session.commit()

    async def sweep_streaming(self) -> int:
        """Flip all ``status='streaming'`` rows to ``'failed'``.

        Called once at startup to recover from a prior crash.
        Returns the number of rows updated.
        """
        async with self._sm() as session:
            stmt = (
                update(MessageModel)
                .where(MessageModel.status == "streaming")
                .values(status="failed")
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0


__all__ = [
    "ConversationModel",
    "ConversationRepo",
    "MessageModel",
    "MessageRepo",
]
