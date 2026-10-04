"""Channel-kind ORM model + repo for ``channel_replies``: which platform messages
make up each bot reply, so the owner can withdraw it later (spec channels
"Withdraw a bot reply on the owner's command").

``runs.db`` holds it, beside the other per-chat history, so a daemon restart
inside a platform's withdraw window loses nothing. Only ids and times are kept —
never the reply's text.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, Index, String, Text, delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.application.channel.store_ports import ReplyRecord
from coffer.infrastructure.persistence.base import Base

__all__ = ["ChannelReplyModel", "ChannelReplyRepo"]


class ChannelReplyModel(Base):
    __tablename__ = "channel_replies"

    reply_id: Mapped[str] = mapped_column(String, primary_key=True)
    resource_uid: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    chat_kind: Mapped[str] = mapped_column(String, nullable=False)
    #: A JSON list of platform message ids, in send order.
    message_ids: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("idx_channel_replies_chat", "resource_uid", "chat_id", "sent_at"),)


def _to_domain(row: ChannelReplyModel) -> ReplyRecord:
    sent_at = row.sent_at if row.sent_at.tzinfo is not None else row.sent_at.replace(tzinfo=UTC)
    return ReplyRecord(
        reply_id=row.reply_id,
        resource_uid=row.resource_uid,
        chat_id=row.chat_id,
        thread_id=row.thread_id,
        chat_kind=row.chat_kind,
        message_ids=tuple(str(i) for i in json.loads(row.message_ids)),
        sent_at=sent_at,
    )


class ChannelReplyRepo:
    """SQLAlchemy implementation of ``ReplyLedgerPort``."""

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def add(self, record: ReplyRecord) -> None:
        async with self._sm() as session:
            session.add(
                ChannelReplyModel(
                    reply_id=record.reply_id,
                    resource_uid=record.resource_uid,
                    chat_id=record.chat_id,
                    thread_id=record.thread_id,
                    chat_kind=record.chat_kind,
                    message_ids=json.dumps(list(record.message_ids)),
                    sent_at=record.sent_at,
                )
            )
            await session.commit()

    async def get(self, reply_id: str) -> ReplyRecord | None:
        async with self._sm() as session:
            row = await session.get(ChannelReplyModel, reply_id)
            return _to_domain(row) if row is not None else None

    async def find_by_message(
        self, resource_uid: str, chat_id: str, message_id: str
    ) -> ReplyRecord | None:
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(ChannelReplyModel)
                    .where(
                        ChannelReplyModel.resource_uid == resource_uid,
                        ChannelReplyModel.chat_id == chat_id,
                    )
                    .order_by(ChannelReplyModel.sent_at.desc())
                )
            ).scalars()
            for row in rows:
                record = _to_domain(row)
                if message_id in record.message_ids:
                    return record
        return None

    async def latest(
        self, resource_uid: str, chat_id: str, thread_id: str | None
    ) -> ReplyRecord | None:
        async with self._sm() as session:
            query = select(ChannelReplyModel).where(
                ChannelReplyModel.resource_uid == resource_uid,
                ChannelReplyModel.chat_id == chat_id,
            )
            if thread_id is not None:
                query = query.where(ChannelReplyModel.thread_id == thread_id)
            row = (
                await session.execute(query.order_by(ChannelReplyModel.sent_at.desc()).limit(1))
            ).scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def remove(self, reply_id: str) -> None:
        async with self._sm() as session:
            await session.execute(
                delete(ChannelReplyModel).where(ChannelReplyModel.reply_id == reply_id)
            )
            await session.commit()

    async def prune(self, before: datetime) -> int:
        async with self._sm() as session:
            result = await session.execute(
                delete(ChannelReplyModel).where(ChannelReplyModel.sent_at < before)
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def delete_for_channel(self, resource_uid: str) -> None:
        async with self._sm() as session:
            await session.execute(
                delete(ChannelReplyModel).where(ChannelReplyModel.resource_uid == resource_uid)
            )
            await session.commit()
