"""Agent-kind ORM models + repos.

Per Contract 5, this module must not import any other kind subpackage.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, String, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class SuppressedAgentTypeModel(Base):
    __tablename__ = "suppressed_agent_types"

    agent_type: Mapped[str] = mapped_column(String, primary_key=True)
    suppressed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


def _tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class SuppressedAgentTypeRepo:
    """CRUD for the auto-detect suppression list."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def is_suppressed(self, agent_type: str) -> bool:
        async with self._sm() as session:
            stmt = select(SuppressedAgentTypeModel).where(
                SuppressedAgentTypeModel.agent_type == agent_type
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return row is not None

    async def list_all(self) -> list[str]:
        async with self._sm() as session:
            stmt = select(SuppressedAgentTypeModel)
            rows = (await session.execute(stmt)).scalars().all()
            return [r.agent_type for r in rows]

    async def suppress(self, agent_type: str, when: datetime | None = None) -> None:
        when = when or datetime.now(tz=UTC)
        async with self._sm() as session:
            existing = await session.get(SuppressedAgentTypeModel, agent_type)
            if existing is not None:
                existing.suppressed_at = when
            else:
                session.add(
                    SuppressedAgentTypeModel(
                        agent_type=agent_type,
                        suppressed_at=when,
                    )
                )
            await session.commit()

    async def unsuppress(self, agent_type: str) -> None:
        async with self._sm() as session:
            existing = await session.get(SuppressedAgentTypeModel, agent_type)
            if existing is None:
                return
            await session.delete(existing)
            await session.commit()
