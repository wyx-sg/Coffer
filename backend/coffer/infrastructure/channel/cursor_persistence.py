"""Channel-kind ORM model + repo for ``channel_thread_cursors``: how far each
conversation has seen each platform thread, so a later turn folds only what is
new (spec channels "Ground a thread turn in a bounded slice of the thread").

``runs.db`` holds it, beside the other per-chat history, so a daemon restart
does not send every thread's next turn back to a full seed. Ids and times only —
never a message's text. Rows name their channel by uid and go with it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, String, and_, delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.application.channel.store_ports import PENDING_CONVERSATION, ThreadCursor
from coffer.infrastructure.persistence.base import Base

__all__ = ["ChannelThreadCursorModel", "ChannelThreadCursorRepo"]


class ChannelThreadCursorModel(Base):
    __tablename__ = "channel_thread_cursors"

    resource_uid: Mapped[str] = mapped_column(String, primary_key=True)
    chat_id: Mapped[str] = mapped_column(String, primary_key=True)
    #: The platform thread the messages live in.
    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    #: "" while the conversation the turn opens does not exist yet.
    conversation_id: Mapped[str] = mapped_column(String, primary_key=True)
    last_message_id: Mapped[str] = mapped_column(String, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_domain(row: ChannelThreadCursorModel) -> ThreadCursor:
    return ThreadCursor(
        resource_uid=row.resource_uid,
        chat_id=row.chat_id,
        thread_id=row.thread_id,
        conversation_id=row.conversation_id,
        last_message_id=row.last_message_id,
        last_message_at=_tz(row.last_message_at),
        updated_at=_tz(row.updated_at),
    )


def _key(
    resource_uid: str, chat_id: str, thread_id: str, conversation_id: str
) -> tuple[str, str, str, str]:
    # The mapper's primary-key order.
    return (resource_uid, chat_id, thread_id, conversation_id)


class ChannelThreadCursorRepo:
    """SQLAlchemy implementation of ``ThreadCursorPort``."""

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def get(
        self, resource_uid: str, chat_id: str, thread_id: str, conversation_id: str
    ) -> ThreadCursor | None:
        async with self._sm() as session:
            row = await session.get(
                ChannelThreadCursorModel, _key(resource_uid, chat_id, thread_id, conversation_id)
            )
            return _to_domain(row) if row is not None else None

    async def put(self, cursor: ThreadCursor) -> None:
        async with self._sm() as session:
            await session.merge(
                ChannelThreadCursorModel(
                    resource_uid=cursor.resource_uid,
                    chat_id=cursor.chat_id,
                    thread_id=cursor.thread_id,
                    conversation_id=cursor.conversation_id,
                    last_message_id=cursor.last_message_id,
                    last_message_at=cursor.last_message_at,
                    updated_at=cursor.updated_at,
                )
            )
            await session.commit()

    async def claim(
        self, resource_uid: str, chat_id: str, thread_id: str, conversation_id: str
    ) -> None:
        if conversation_id == PENDING_CONVERSATION:
            return
        async with self._sm() as session:
            pending = await session.get(
                ChannelThreadCursorModel,
                _key(resource_uid, chat_id, thread_id, PENDING_CONVERSATION),
            )
            if pending is None:
                return
            own = await session.get(
                ChannelThreadCursorModel, _key(resource_uid, chat_id, thread_id, conversation_id)
            )
            if own is None:
                session.add(
                    ChannelThreadCursorModel(
                        resource_uid=resource_uid,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        conversation_id=conversation_id,
                        last_message_id=pending.last_message_id,
                        last_message_at=pending.last_message_at,
                        updated_at=pending.updated_at,
                    )
                )
            await session.delete(pending)
            await session.commit()

    async def list_for_thread(
        self, resource_uid: str, chat_id: str, thread_id: str
    ) -> list[ThreadCursor]:
        """Every conversation's cursor into one thread (for tests and diagnosis)."""
        async with self._sm() as session:
            rows = await session.scalars(
                select(ChannelThreadCursorModel).where(
                    and_(
                        ChannelThreadCursorModel.resource_uid == resource_uid,
                        ChannelThreadCursorModel.chat_id == chat_id,
                        ChannelThreadCursorModel.thread_id == thread_id,
                    )
                )
            )
            return [_to_domain(r) for r in rows]

    async def delete_for_channel(self, resource_uid: str) -> None:
        async with self._sm() as session:
            await session.execute(
                delete(ChannelThreadCursorModel).where(
                    ChannelThreadCursorModel.resource_uid == resource_uid
                )
            )
            await session.commit()
