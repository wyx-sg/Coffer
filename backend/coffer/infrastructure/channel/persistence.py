"""Channel-kind ORM model + repo (channel_peers).

Registers against the shared ``Base.metadata``. Per Contract 5 this module
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
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.application.channel.ports import ChannelPeer, ChannelThreadConversation
from coffer.infrastructure.persistence.base import Base


class ChannelPeerModel(Base):
    __tablename__ = "channel_peers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    paired_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("resource_id", "chat_id", name="uq_channel_peers_resource_chat"),
        Index("idx_channel_peers_resource", "resource_id"),
    )


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

    __table_args__ = (
        UniqueConstraint(
            "resource_id",
            "chat_id",
            "thread_id",
            name="uq_channel_thread_conv_resource_chat_thread",
        ),
        Index("idx_channel_thread_conv_resource", "resource_id"),
    )


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_domain(row: ChannelPeerModel) -> ChannelPeer:
    return ChannelPeer(
        resource_id=row.resource_id,
        chat_id=row.chat_id,
        display_name=row.display_name,
        paired_at=_tz(row.paired_at),
        sender_id=row.sender_id,
    )


class ChannelPeerRepo:
    """SQLAlchemy implementation of ``ChannelPeerRepoPort``.

    A channel may have several peer rows — one per DM/group/thread it has
    been paired to (``UniqueConstraint("resource_id", "chat_id")``).
    ``upsert`` re-pairs a single ``(resource_id, chat_id)`` row without
    disturbing any other chat paired to the same channel. Every read either
    names its chat (``get_by_chat``) or says which of several it wants
    (``owner_peer``, ``list_by_resource``): a read that names neither is how a
    private notification ended up in a group chat.
    """

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def owner_peer(self, resource_id: int) -> ChannelPeer | None:
        """The earliest-paired chat — see ``ChannelPeerRepoPort.owner_peer``.

        ``chat_id`` breaks a ``paired_at`` tie so the answer is the same on
        every call and on every machine that converged the same pairings.
        """
        async with self._sm() as session:
            row = (
                (
                    await session.execute(
                        select(ChannelPeerModel)
                        .where(ChannelPeerModel.resource_id == resource_id)
                        .order_by(ChannelPeerModel.paired_at, ChannelPeerModel.chat_id)
                    )
                )
                .scalars()
                .first()
            )
            return _to_domain(row) if row is not None else None

    async def get_by_chat(self, resource_id: int, chat_id: str) -> ChannelPeer | None:
        async with self._sm() as session:
            row = (
                await session.execute(
                    select(ChannelPeerModel).where(
                        ChannelPeerModel.resource_id == resource_id,
                        ChannelPeerModel.chat_id == chat_id,
                    )
                )
            ).scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def list_by_resource(self, resource_id: int) -> list[ChannelPeer]:
        async with self._sm() as session:
            rows = (
                (
                    await session.execute(
                        select(ChannelPeerModel).where(ChannelPeerModel.resource_id == resource_id)
                    )
                )
                .scalars()
                .all()
            )
            return [_to_domain(row) for row in rows]

    async def owner_sender_id(self, resource_id: int) -> str | None:
        async with self._sm() as session:
            row = (
                (
                    await session.execute(
                        select(ChannelPeerModel)
                        .where(
                            ChannelPeerModel.resource_id == resource_id,
                            ChannelPeerModel.sender_id.isnot(None),
                        )
                        .order_by(ChannelPeerModel.id)
                    )
                )
                .scalars()
                .first()
            )
            return row.sender_id if row is not None else None

    async def upsert(self, peer: ChannelPeer) -> None:
        async with self._sm() as session:
            await session.execute(
                delete(ChannelPeerModel).where(
                    ChannelPeerModel.resource_id == peer.resource_id,
                    ChannelPeerModel.chat_id == peer.chat_id,
                )
            )
            session.add(
                ChannelPeerModel(
                    resource_id=peer.resource_id,
                    chat_id=peer.chat_id,
                    display_name=peer.display_name,
                    paired_at=peer.paired_at,
                    sender_id=peer.sender_id,
                )
            )
            await session.commit()

    async def delete_by_chat(self, resource_id: int, chat_id: str) -> None:
        """Un-pair one chat. A no-op when it is already gone — two machines
        un-pairing the same chat is agreement, not a failure."""
        async with self._sm() as session:
            await session.execute(
                delete(ChannelPeerModel).where(
                    ChannelPeerModel.resource_id == resource_id,
                    ChannelPeerModel.chat_id == chat_id,
                )
            )
            await session.commit()


def _thread_to_domain(row: ChannelThreadConversationModel) -> ChannelThreadConversation:
    return ChannelThreadConversation(
        resource_id=row.resource_id,
        chat_id=row.chat_id,
        thread_id=row.thread_id,
        active_conversation_id=row.active_conversation_id,
        preferred_agent=row.preferred_agent,
        updated_at=_tz(row.updated_at),
    )


class ChannelThreadConversationRepo:
    """SQLAlchemy implementation of ``ChannelThreadConversationRepoPort`` (FR-032).

    Conversation identity is keyed by ``(resource_id, chat_id, thread_id)`` so
    each group thread (and the DM, ``thread_id=""``) drives its own conversation
    with its own turn lock. ``set_active_conversation`` and ``set_preferred_agent``
    each upsert one field of the row, leaving the other untouched — a thread's
    sticky agent survives opening a fresh conversation and vice versa.
    """

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def get(
        self, resource_id: int, chat_id: str, thread_id: str
    ) -> ChannelThreadConversation | None:
        async with self._sm() as session:
            row = (
                await session.execute(
                    select(ChannelThreadConversationModel).where(
                        ChannelThreadConversationModel.resource_id == resource_id,
                        ChannelThreadConversationModel.chat_id == chat_id,
                        ChannelThreadConversationModel.thread_id == thread_id,
                    )
                )
            ).scalar_one_or_none()
            return _thread_to_domain(row) if row is not None else None

    async def set_active_conversation(
        self, resource_id: int, chat_id: str, thread_id: str, conversation_id: str | None
    ) -> None:
        async with self._sm() as session:
            row = await self._row_for_update(session, resource_id, chat_id, thread_id)
            if row is None:
                session.add(
                    ChannelThreadConversationModel(
                        resource_id=resource_id,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        active_conversation_id=conversation_id,
                        preferred_agent=None,
                        updated_at=datetime.now(tz=UTC),
                    )
                )
            else:
                row.active_conversation_id = conversation_id
                row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def set_preferred_agent(
        self, resource_id: int, chat_id: str, thread_id: str, preferred_agent: str | None
    ) -> None:
        async with self._sm() as session:
            row = await self._row_for_update(session, resource_id, chat_id, thread_id)
            if row is None:
                session.add(
                    ChannelThreadConversationModel(
                        resource_id=resource_id,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        active_conversation_id=None,
                        preferred_agent=preferred_agent,
                        updated_at=datetime.now(tz=UTC),
                    )
                )
            else:
                row.preferred_agent = preferred_agent
                row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    @staticmethod
    async def _row_for_update(
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
