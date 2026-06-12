"""Persistence for memory projection bindings (spec 007, agent layer).

A binding records that an agent has a native memory projection established for a
memory store, so the projection engine can re-render on memory changes and the
agent-detail surfaces can list/remove it. The ORM model registers against the
shared ``Base.metadata`` (Alembic discovers it via ``models`` import).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, Boolean, Index, String, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class MemoryProjectionBindingModel(Base):
    __tablename__ = "memory_projection_bindings"

    store_name: Mapped[str] = mapped_column(String, primary_key=True)
    agent_ref: Mapped[str] = mapped_column(String, primary_key=True)
    projection_mode: Mapped[str] = mapped_column(String, nullable=False)
    target_path: Mapped[str] = mapped_column(String, nullable=False)
    native_memory_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (Index("idx_projection_bindings_agent", "agent_ref"),)


@dataclass(frozen=True)
class ProjectionBinding:
    """One established projection (store ↔ agent)."""

    store_name: str
    agent_ref: str
    projection_mode: str
    target_path: str
    native_memory_disabled: bool


class ProjectionBindingRepo:
    """CRUD over ``memory_projection_bindings``."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def upsert(self, binding: ProjectionBinding) -> None:
        async with self._sm() as session:
            stmt = select(MemoryProjectionBindingModel).where(
                MemoryProjectionBindingModel.store_name == binding.store_name,
                MemoryProjectionBindingModel.agent_ref == binding.agent_ref,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                session.add(
                    MemoryProjectionBindingModel(
                        store_name=binding.store_name,
                        agent_ref=binding.agent_ref,
                        projection_mode=binding.projection_mode,
                        target_path=binding.target_path,
                        native_memory_disabled=binding.native_memory_disabled,
                        created_at=datetime.now(tz=UTC),
                    )
                )
            else:
                row.projection_mode = binding.projection_mode
                row.target_path = binding.target_path
                row.native_memory_disabled = binding.native_memory_disabled
            await session.commit()

    async def list_for_store(self, store_name: str) -> list[ProjectionBinding]:
        async with self._sm() as session:
            stmt = select(MemoryProjectionBindingModel).where(
                MemoryProjectionBindingModel.store_name == store_name
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(r) for r in rows]

    async def list_for_agent(self, agent_ref: str) -> list[ProjectionBinding]:
        async with self._sm() as session:
            stmt = select(MemoryProjectionBindingModel).where(
                MemoryProjectionBindingModel.agent_ref == agent_ref
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(r) for r in rows]

    async def all_bindings(self) -> list[ProjectionBinding]:
        async with self._sm() as session:
            rows = (await session.execute(select(MemoryProjectionBindingModel))).scalars().all()
            return [_to_domain(r) for r in rows]

    async def get(self, store_name: str, agent_ref: str) -> ProjectionBinding | None:
        async with self._sm() as session:
            stmt = select(MemoryProjectionBindingModel).where(
                MemoryProjectionBindingModel.store_name == store_name,
                MemoryProjectionBindingModel.agent_ref == agent_ref,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_domain(row) if row else None

    async def delete(self, store_name: str, agent_ref: str) -> bool:
        async with self._sm() as session:
            stmt = sa_delete(MemoryProjectionBindingModel).where(
                MemoryProjectionBindingModel.store_name == store_name,
                MemoryProjectionBindingModel.agent_ref == agent_ref,
            )
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) > 0


def _to_domain(row: MemoryProjectionBindingModel) -> ProjectionBinding:
    return ProjectionBinding(
        store_name=row.store_name,
        agent_ref=row.agent_ref,
        projection_mode=row.projection_mode,
        target_path=row.target_path,
        native_memory_disabled=row.native_memory_disabled,
    )
