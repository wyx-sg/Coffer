"""Channel-kind ORM model + repo for ``channel_outbox``: messages Coffer owes a
chat and has not delivered yet (spec chat "Mirror a web reply into the channel
it came from").

A reply typed on the Chat page into a channel's conversation is sent to that
chat at once when it can be; when it cannot — the channel is not running, the
platform refused — it waits here, with the agent's answer behind it, until the
runtime finds the channel running again. A row is marked delivered, never
deleted by a failure, so nothing the owner wrote is lost to a dropped
connection. Rows hang off ``resources.id`` and go with the channel.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Integer, String, Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.application.channel.store_ports import OutboxEntry
from coffer.infrastructure.persistence.base import Base

__all__ = ["ChannelOutboxModel", "ChannelOutboxRepo"]


class ChannelOutboxModel(Base):
    __tablename__ = "channel_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    chat_kind: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    #: "reply" (typed on the web) or "answer" (the agent's reply to it).
    kind: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    #: NULL while pending.
    delivered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_channel_outbox_pending", "resource_id", "delivered_at"),
        Index("idx_channel_outbox_conversation", "conversation_id"),
    )


def _tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_domain(row: ChannelOutboxModel) -> OutboxEntry:
    return OutboxEntry(
        id=row.id,
        resource_id=row.resource_id,
        chat_id=row.chat_id,
        thread_id=row.thread_id,
        chat_kind=row.chat_kind,
        conversation_id=row.conversation_id,
        kind=row.kind,
        text=row.text,
        created_at=_tz(row.created_at),
    )


class ChannelOutboxRepo:
    """SQLAlchemy implementation of ``ChannelOutboxRepoPort``."""

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def add(
        self,
        *,
        resource_id: int,
        chat_id: str,
        thread_id: str,
        chat_kind: str,
        conversation_id: str,
        kind: str,
        text: str,
    ) -> int:
        async with self._sm() as session:
            row = ChannelOutboxModel(
                resource_id=resource_id,
                chat_id=chat_id,
                thread_id=thread_id,
                chat_kind=chat_kind,
                conversation_id=conversation_id,
                kind=kind,
                text=text,
                created_at=datetime.now(tz=UTC),
            )
            session.add(row)
            await session.commit()
            return int(row.id)

    async def pending(self, resource_id: int) -> list[OutboxEntry]:
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(ChannelOutboxModel)
                    .where(
                        ChannelOutboxModel.resource_id == resource_id,
                        ChannelOutboxModel.delivered_at.is_(None),
                    )
                    .order_by(ChannelOutboxModel.id)
                )
            ).scalars()
            return [_to_domain(row) for row in rows]

    async def pending_for_conversation(self, conversation_id: str) -> list[OutboxEntry]:
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(ChannelOutboxModel)
                    .where(
                        ChannelOutboxModel.conversation_id == conversation_id,
                        ChannelOutboxModel.delivered_at.is_(None),
                    )
                    .order_by(ChannelOutboxModel.id)
                )
            ).scalars()
            return [_to_domain(row) for row in rows]

    async def mark_delivered(self, entry_id: int) -> None:
        async with self._sm() as session:
            row = await session.get(ChannelOutboxModel, entry_id)
            if row is not None and row.delivered_at is None:
                row.delivered_at = datetime.now(tz=UTC)
                await session.commit()
