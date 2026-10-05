"""Channel-kind ORM model + repo for ``channel_outbox``.

The table once held messages Coffer owed a chat and had not delivered yet (a
reply typed on the web, mirrored into the channel it came from). The web reply
is gone, so nothing writes the table any more; it stays so a database that
holds rows keeps them until their channel is deleted, which is the one thing
the repo still does. Rows name their channel by uid.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, Index, Integer, String, Text, delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base

__all__ = ["ChannelOutboxModel", "ChannelOutboxRepo"]


class ChannelOutboxModel(Base):
    __tablename__ = "channel_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_uid: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    chat_kind: Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    #: "reply" or "answer" (what the retired web-reply mirror wrote).
    kind: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    #: NULL while pending.
    delivered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_channel_outbox_pending", "resource_uid", "delivered_at"),
        Index("idx_channel_outbox_conversation", "conversation_id"),
    )


class ChannelOutboxRepo:
    """Deletes a deleted channel's outbox rows."""

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def delete_for_channel(self, resource_uid: str) -> None:
        """Drop a deleted channel's rows, delivered or not: there is no chat
        left to deliver them to."""
        async with self._sm() as session:
            await session.execute(
                delete(ChannelOutboxModel).where(ChannelOutboxModel.resource_uid == resource_uid)
            )
            await session.commit()
