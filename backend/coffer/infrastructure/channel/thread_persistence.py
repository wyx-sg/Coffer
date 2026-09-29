"""Channel-kind ORM models + repo for what each chat thread is doing:
``channel_thread_conversations`` (the conversation a thread is bound to and the
settings it keeps) and ``channel_thread_history`` (every conversation it ever
opened, for `/resume` and for mirroring a web reply back to it).

Split out of ``persistence`` for its size budget; per Contract 5 this module
must not import from any other kind module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.application.channel.store_ports import (
    KEEP,
    ChannelThreadConversation,
    ChannelThreadLocation,
)
from coffer.infrastructure.persistence.base import Base

__all__ = [
    "ChannelThreadConversationModel",
    "ChannelThreadConversationRepo",
    "ChannelThreadHistoryModel",
]


class ChannelThreadConversationModel(Base):
    __tablename__ = "channel_thread_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    # "" is the DM (or a group's main chat); each group thread is its own row.
    thread_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    active_conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # A parallel thread `/thread` opened carries its number within the chat and
    # its title (see "Open parallel conversations beside a direct chat"); NULL on
    # every other row.
    parallel_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parallel_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "direct" / "group": which send path reaches the thread (migration 0108).
    chat_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    # The thread's sticky model, effort and working directory (migration 0108).
    preferred_model: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_effort: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_cwd: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "chat_id",
            "thread_id",
            name="uq_channel_thread_conv_resource_chat_thread",
        ),
        Index("idx_channel_thread_conv_resource", "resource_id"),
    )


class ChannelThreadHistoryModel(Base):
    """One conversation a chat thread opened (migration 0108)."""

    __tablename__ = "channel_thread_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    chat_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_channel_thread_history_conversation"),
        Index("idx_channel_thread_history_thread", "resource_id", "chat_id", "thread_id"),
    )


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _thread_to_domain(row: ChannelThreadConversationModel) -> ChannelThreadConversation:
    return ChannelThreadConversation(
        resource_id=row.resource_id,
        chat_id=row.chat_id,
        thread_id=row.thread_id,
        active_conversation_id=row.active_conversation_id,
        preferred_agent=row.preferred_agent,
        updated_at=_tz(row.updated_at),
        parallel_ordinal=row.parallel_ordinal,
        parallel_title=row.parallel_title,
        chat_kind=row.chat_kind,
        preferred_model=row.preferred_model,
        preferred_effort=row.preferred_effort,
        preferred_cwd=row.preferred_cwd,
    )


class ChannelThreadConversationRepo:
    """SQLAlchemy implementation of ``ChannelThreadConversationRepoPort``.

    See "Key conversation identity by channel, chat and thread".

    Conversation identity is keyed by ``(resource_id, chat_id, thread_id)`` so
    each group thread (and the DM, ``thread_id=""``) drives its own conversation
    with its own turn lock. Every write upserts only the fields it names,
    leaving the rest of the row untouched — a thread's sticky settings survive
    opening a fresh conversation and vice versa.
    """

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def get(
        self, resource_id: int, chat_id: str, thread_id: str
    ) -> ChannelThreadConversation | None:
        async with self._sm() as session:
            row = await self._row(session, resource_id, chat_id, thread_id)
            return _thread_to_domain(row) if row is not None else None

    async def set_active_conversation(
        self, resource_id: int, chat_id: str, thread_id: str, conversation_id: str | None
    ) -> None:
        await self._upsert(resource_id, chat_id, thread_id, active_conversation_id=conversation_id)

    async def set_preferred_agent(
        self, resource_id: int, chat_id: str, thread_id: str, preferred_agent: str | None
    ) -> None:
        await self._upsert(resource_id, chat_id, thread_id, preferred_agent=preferred_agent)

    async def set_preferences(
        self,
        resource_id: int,
        chat_id: str,
        thread_id: str,
        *,
        agent: str | None = KEEP,
        model: str | None = KEEP,
        effort: str | None = KEEP,
        cwd: str | None = KEEP,
    ) -> None:
        fields = {
            "preferred_agent": agent,
            "preferred_model": model,
            "preferred_effort": effort,
            "preferred_cwd": cwd,
        }
        await self._upsert(
            resource_id,
            chat_id,
            thread_id,
            **{key: value for key, value in fields.items() if value is not KEEP},
        )

    async def note_chat_kind(
        self, resource_id: int, chat_id: str, thread_id: str, chat_kind: str
    ) -> None:
        await self._upsert(resource_id, chat_id, thread_id, chat_kind=chat_kind)

    async def next_parallel_ordinal(self, resource_id: int, chat_id: str) -> int:
        # Over every row of the chat, not only live ones: a number stays taken
        # after its conversation is replaced, so a mark never names two threads.
        async with self._sm() as session:
            highest = (
                await session.execute(
                    select(func.max(ChannelThreadConversationModel.parallel_ordinal)).where(
                        ChannelThreadConversationModel.resource_id == resource_id,
                        ChannelThreadConversationModel.chat_id == chat_id,
                    )
                )
            ).scalar_one_or_none()
            return int(highest or 0) + 1

    async def open_parallel(
        self, resource_id: int, chat_id: str, thread_id: str, ordinal: int, title: str
    ) -> None:
        await self._upsert(
            resource_id, chat_id, thread_id, parallel_ordinal=ordinal, parallel_title=title
        )

    async def list_parallel(
        self, resource_id: int, chat_id: str
    ) -> list[ChannelThreadConversation]:
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(ChannelThreadConversationModel)
                    .where(
                        ChannelThreadConversationModel.resource_id == resource_id,
                        ChannelThreadConversationModel.chat_id == chat_id,
                        ChannelThreadConversationModel.parallel_ordinal.is_not(None),
                    )
                    .order_by(ChannelThreadConversationModel.parallel_ordinal.desc())
                )
            ).scalars()
            return [_thread_to_domain(row) for row in rows]

    # -- history ---------------------------------------------------------------

    async def record_history(
        self,
        resource_id: int,
        chat_id: str,
        thread_id: str,
        conversation_id: str,
        chat_kind: str | None,
    ) -> None:
        async with self._sm() as session:
            existing = (
                await session.execute(
                    select(ChannelThreadHistoryModel).where(
                        ChannelThreadHistoryModel.conversation_id == conversation_id
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                if chat_kind and not existing.chat_kind:
                    existing.chat_kind = chat_kind
                    await session.commit()
                return
            session.add(
                ChannelThreadHistoryModel(
                    resource_id=resource_id,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    conversation_id=conversation_id,
                    chat_kind=chat_kind,
                    opened_at=datetime.now(tz=UTC),
                )
            )
            await session.commit()

    async def history(
        self, resource_id: int, chat_id: str, thread_id: str, *, limit: int = 20
    ) -> list[str]:
        async with self._sm() as session:
            rows = (
                await session.execute(
                    select(ChannelThreadHistoryModel.conversation_id)
                    .where(
                        ChannelThreadHistoryModel.resource_id == resource_id,
                        ChannelThreadHistoryModel.chat_id == chat_id,
                        ChannelThreadHistoryModel.thread_id == thread_id,
                    )
                    .order_by(ChannelThreadHistoryModel.id.desc())
                    .limit(limit)
                )
            ).scalars()
            return list(rows)

    async def locate(self, conversation_id: str) -> ChannelThreadLocation | None:
        async with self._sm() as session:
            row = (
                await session.execute(
                    select(ChannelThreadHistoryModel).where(
                        ChannelThreadHistoryModel.conversation_id == conversation_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            chat_kind = row.chat_kind
            if chat_kind is None:
                # Recorded before the thread's kind was known; the thread row may
                # have learnt it since from a later message.
                thread = await self._row(session, row.resource_id, row.chat_id, row.thread_id)
                chat_kind = thread.chat_kind if thread is not None else None
            return ChannelThreadLocation(
                resource_id=row.resource_id,
                chat_id=row.chat_id,
                thread_id=row.thread_id,
                chat_kind=chat_kind,
                opened_at=_tz(row.opened_at),
            )

    # -- helpers ---------------------------------------------------------------

    async def _upsert(self, resource_id: int, chat_id: str, thread_id: str, **fields: Any) -> None:
        async with self._sm() as session:
            row = await self._row(session, resource_id, chat_id, thread_id)
            if row is None:
                row = ChannelThreadConversationModel(
                    resource_id=resource_id, chat_id=chat_id, thread_id=thread_id
                )
                session.add(row)
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    @staticmethod
    async def _row(
        session: Any, resource_id: int, chat_id: str, thread_id: str
    ) -> ChannelThreadConversationModel | None:
        row: ChannelThreadConversationModel | None = (
            await session.execute(
                select(ChannelThreadConversationModel).where(
                    ChannelThreadConversationModel.resource_id == resource_id,
                    ChannelThreadConversationModel.chat_id == chat_id,
                    ChannelThreadConversationModel.thread_id == thread_id,
                )
            )
        ).scalar_one_or_none()
        return row
