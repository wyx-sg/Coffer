"""Channel-kind ORM model + repo (channel_peers).

Registers against the shared ``Base.metadata``. Per Contract 5 this module
must not import from any other kind module.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    delete,
    select,
    update,
)
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.application.channel.ports import ChannelPeer
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
    active_conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sender_id: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_agent: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("resource_id", "chat_id", name="uq_channel_peers_resource_chat"),
        Index("idx_channel_peers_resource", "resource_id"),
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
        active_conversation_id=row.active_conversation_id,
        sender_id=row.sender_id,
        preferred_agent=row.preferred_agent,
    )


class ChannelPeerRepo:
    """SQLAlchemy implementation of ``ChannelPeerRepoPort``.

    A channel may have several peer rows — one per DM/group/thread it has
    been paired to (``UniqueConstraint("resource_id", "chat_id")``).
    ``upsert`` re-pairs a single ``(resource_id, chat_id)`` row without
    disturbing any other chat paired to the same channel; ``get`` remains the
    legacy single-peer accessor for callers that only ever address a
    channel's DM peer.
    """

    def __init__(self, session_maker: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = session_maker

    async def get(self, resource_id: int) -> ChannelPeer | None:
        async with self._sm() as session:
            row = (
                (
                    await session.execute(
                        select(ChannelPeerModel).where(ChannelPeerModel.resource_id == resource_id)
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
                    active_conversation_id=peer.active_conversation_id,
                    sender_id=peer.sender_id,
                    preferred_agent=peer.preferred_agent,
                )
            )
            await session.commit()

    async def set_active_conversation(
        self, resource_id: int, chat_id: str, conversation_id: str | None
    ) -> None:
        async with self._sm() as session:
            await session.execute(
                update(ChannelPeerModel)
                .where(
                    ChannelPeerModel.resource_id == resource_id,
                    ChannelPeerModel.chat_id == chat_id,
                )
                .values(active_conversation_id=conversation_id)
            )
            await session.commit()

    async def set_preferences(
        self,
        resource_id: int,
        *,
        preferred_agent: str | None,
    ) -> None:
        async with self._sm() as session:
            await session.execute(
                update(ChannelPeerModel)
                .where(ChannelPeerModel.resource_id == resource_id)
                .values(
                    preferred_agent=preferred_agent,
                )
            )
            await session.commit()
