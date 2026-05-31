"""ORM + repo for the `memory_records` table (memory kind)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, Index, PrimaryKeyConstraint, String, Text, func, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.memory.record import Actor, MemoryRecord
from coffer.infrastructure.persistence.base import Base


class MemoryRecordModel(Base):
    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(String, nullable=False)
    store_name: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("store_name", "id", name="pk_memory_records"),
        Index("idx_memory_records_store_time", "store_name", "created_at"),
    )


def _tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_domain(row: MemoryRecordModel) -> MemoryRecord:
    return MemoryRecord(
        id=row.id,
        store_name=row.store_name,
        text=row.text,
        actor=row.actor,  # type: ignore[arg-type]
        created_at=_tz(row.created_at),
        updated_at=_tz(row.updated_at),
    )


class SqlAlchemyMemoryRecordRepo:
    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def create(self, m: MemoryRecord) -> MemoryRecord:
        async with self._sm() as session:
            row = MemoryRecordModel(
                id=m.id,
                store_name=m.store_name,
                text=m.text,
                actor=m.actor,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def get(self, store_name: str, memory_id: str) -> MemoryRecord | None:
        async with self._sm() as session:
            stmt = select(MemoryRecordModel).where(
                MemoryRecordModel.store_name == store_name,
                MemoryRecordModel.id == memory_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_domain(row) if row else None

    async def list_by_store(
        self, store_name: str, *, limit: int, offset: int
    ) -> list[MemoryRecord]:
        async with self._sm() as session:
            stmt = (
                select(MemoryRecordModel)
                .where(MemoryRecordModel.store_name == store_name)
                .order_by(MemoryRecordModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(r) for r in rows]

    async def count_by_store(self, store_name: str) -> int:
        async with self._sm() as session:
            stmt = (
                select(func.count())
                .select_from(MemoryRecordModel)
                .where(MemoryRecordModel.store_name == store_name)
            )
            return int((await session.execute(stmt)).scalar_one())

    async def update_text(
        self,
        store_name: str,
        memory_id: str,
        new_text: str,
        updated_at: datetime,
    ) -> MemoryRecord:
        async with self._sm() as session:
            stmt = select(MemoryRecordModel).where(
                MemoryRecordModel.store_name == store_name,
                MemoryRecordModel.id == memory_id,
            )
            row = (await session.execute(stmt)).scalar_one()
            row.text = new_text
            row.updated_at = updated_at
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def delete(self, store_name: str, memory_id: str) -> bool:
        async with self._sm() as session:
            stmt = sa_delete(MemoryRecordModel).where(
                MemoryRecordModel.store_name == store_name,
                MemoryRecordModel.id == memory_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) > 0

    async def delete_all_by_store(self, store_name: str) -> int:
        async with self._sm() as session:
            stmt = sa_delete(MemoryRecordModel).where(MemoryRecordModel.store_name == store_name)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0


__all__ = [
    "Actor",
    "MemoryRecordModel",
    "SqlAlchemyMemoryRecordRepo",
]
