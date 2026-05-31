"""SQLAlchemy models + repos for conversations and messages (spec 008).

Registers against the shared ``Base.metadata`` so Alembic discovers the tables
(see migrations/env.py). Conversations carry a stable string id (used in URLs);
messages use an integer ``seq`` primary key for cheap insertion ordering plus a
public string ``mid``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.chat.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageStatus,
    ToolCall,
)
from coffer.domain.errors import ConversationNotFound
from coffer.infrastructure.persistence.base import Base


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    target_ref: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    model_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("idx_conversations_status_updated", "status", "updated_at"),)


class MessageModel(Base):
    __tablename__ = "messages"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mid: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("idx_messages_conversation_seq", "conversation_id", "seq"),)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


def _conv_to_domain(row: ConversationModel) -> Conversation:
    return Conversation(
        id=row.id,
        target_ref=row.target_ref,
        title=row.title,
        status=ConversationStatus(row.status),
        model_snapshot=json.loads(row.model_snapshot_json),
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _tool_calls_to_domain(raw: str) -> list[ToolCall]:
    return [
        ToolCall(
            id=str(d["id"]),
            tool=str(d["tool"]),
            args_summary=str(d.get("args_summary", "")),
            result_summary=d.get("result_summary"),
            confirmed=d.get("confirmed"),
        )
        for d in json.loads(raw)
    ]


def _msg_to_domain(row: MessageModel) -> Message:
    return Message(
        id=row.mid,
        conversation_id=row.conversation_id,
        role=MessageRole(row.role),
        content=row.content,
        status=MessageStatus(row.status),
        created_at=_aware(row.created_at),
        tool_calls=_tool_calls_to_domain(row.tool_calls_json),
        error=json.loads(row.error_json) if row.error_json else None,
    )


def _tool_calls_to_json(tool_calls: list[ToolCall]) -> str:
    return json.dumps(
        [
            {
                "id": t.id,
                "tool": t.tool,
                "args_summary": t.args_summary,
                "result_summary": t.result_summary,
                "confirmed": t.confirmed,
            }
            for t in tool_calls
        ]
    )


class SqlAlchemyConversationRepo:
    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def create(self, conversation: Conversation) -> Conversation:
        async with self._sm() as session:
            row = ConversationModel(
                id=conversation.id,
                target_ref=conversation.target_ref,
                title=conversation.title,
                status=conversation.status.value,
                model_snapshot_json=json.dumps(conversation.model_snapshot),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _conv_to_domain(row)

    async def get(self, conversation_id: str) -> Conversation | None:
        async with self._sm() as session:
            row = (
                await session.execute(
                    select(ConversationModel).where(ConversationModel.id == conversation_id)
                )
            ).scalar_one_or_none()
            return _conv_to_domain(row) if row else None

    async def list(
        self,
        *,
        status: ConversationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        async with self._sm() as session:
            stmt = select(ConversationModel).order_by(ConversationModel.updated_at.desc())
            if status is not None:
                stmt = stmt.where(ConversationModel.status == status.value)
            stmt = stmt.limit(limit).offset(offset)
            rows = (await session.execute(stmt)).scalars().all()
            return [_conv_to_domain(r) for r in rows]

    async def _require(self, session: Any, conversation_id: str) -> ConversationModel:
        row: ConversationModel | None = (
            await session.execute(
                select(ConversationModel).where(ConversationModel.id == conversation_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise ConversationNotFound(conversation_id)
        return row

    async def set_title(self, conversation_id: str, title: str) -> Conversation:
        async with self._sm() as session:
            row = await self._require(session, conversation_id)
            row.title = title
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()
            await session.refresh(row)
            return _conv_to_domain(row)

    async def set_status(self, conversation_id: str, status: ConversationStatus) -> Conversation:
        async with self._sm() as session:
            row = await self._require(session, conversation_id)
            row.status = status.value
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()
            await session.refresh(row)
            return _conv_to_domain(row)

    async def touch(self, conversation_id: str) -> None:
        async with self._sm() as session:
            row = await self._require(session, conversation_id)
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def delete(self, conversation_id: str) -> None:
        async with self._sm() as session:
            row = (
                await session.execute(
                    select(ConversationModel).where(ConversationModel.id == conversation_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return  # idempotent
            await session.delete(row)
            await session.commit()


class SqlAlchemyMessageRepo:
    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def add(self, message: Message) -> Message:
        async with self._sm() as session:
            row = MessageModel(
                mid=message.id,
                conversation_id=message.conversation_id,
                role=message.role.value,
                content=message.content,
                tool_calls_json=_tool_calls_to_json(message.tool_calls),
                status=message.status.value,
                error_json=json.dumps(message.error) if message.error else None,
                created_at=message.created_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _msg_to_domain(row)

    async def list_for(self, conversation_id: str) -> list[Message]:
        async with self._sm() as session:
            rows = (
                (
                    await session.execute(
                        select(MessageModel)
                        .where(MessageModel.conversation_id == conversation_id)
                        .order_by(MessageModel.seq.asc())
                    )
                )
                .scalars()
                .all()
            )
            return [_msg_to_domain(r) for r in rows]

    async def update(
        self,
        message_id: str,
        *,
        content: str | None = None,
        status: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        error: dict[str, Any] | None = None,
    ) -> Message:
        async with self._sm() as session:
            row = (
                await session.execute(select(MessageModel).where(MessageModel.mid == message_id))
            ).scalar_one_or_none()
            if row is None:
                raise ConversationNotFound(message_id)
            if content is not None:
                row.content = content
            if status is not None:
                row.status = status
            if tool_calls is not None:
                row.tool_calls_json = json.dumps(tool_calls)
            if error is not None:
                row.error_json = json.dumps(error)
            await session.commit()
            await session.refresh(row)
            return _msg_to_domain(row)
