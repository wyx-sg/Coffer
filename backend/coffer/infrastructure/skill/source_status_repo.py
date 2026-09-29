"""``skill_source_status`` — one row per Git-imported skill, machine-local.

Spec skill-manager "Update a Git-imported skill from its source". The row is
an observation (when this machine last checked, what it found), not vault
state: nothing in the sync bundle reads this table, and the row goes with its
skill (``ON DELETE CASCADE``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.skill.source_status import SourceStatus
from coffer.infrastructure.persistence.base import Base


class SkillSourceStatusModel(Base):
    __tablename__ = "skill_source_status"

    skill_resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )
    checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    commits_ahead: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dismissed_commit: Mapped[str | None] = mapped_column(String, nullable=True)


def _tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_domain(row: SkillSourceStatusModel) -> SourceStatus:
    return SourceStatus(
        skill_resource_id=row.skill_resource_id,
        checked_at=_tz(row.checked_at),
        last_success_at=_tz(row.last_success_at),
        error=row.error,
        latest_commit=row.latest_commit,
        commits_ahead=row.commits_ahead,
        files_changed=row.files_changed,
        dismissed_commit=row.dismissed_commit,
    )


class SkillSourceStatusRepo:
    def __init__(self, sm: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sm

    async def get(self, skill_id: int) -> SourceStatus | None:
        async with self._sm() as session:
            row = await session.get(SkillSourceStatusModel, skill_id)
            return _to_domain(row) if row else None

    async def list_all(self) -> dict[int, SourceStatus]:
        async with self._sm() as session:
            rows = (await session.execute(select(SkillSourceStatusModel))).scalars().all()
            return {r.skill_resource_id: _to_domain(r) for r in rows}

    async def put(self, status: SourceStatus) -> SourceStatus:
        async with self._sm() as session, session.begin():
            row = await session.get(SkillSourceStatusModel, status.skill_resource_id)
            if row is None:
                row = SkillSourceStatusModel(skill_resource_id=status.skill_resource_id)
                session.add(row)
            row.checked_at = status.checked_at
            row.last_success_at = status.last_success_at
            row.error = status.error
            row.latest_commit = status.latest_commit
            row.commits_ahead = status.commits_ahead
            row.files_changed = status.files_changed
            row.dismissed_commit = status.dismissed_commit
        return status

    async def delete(self, skill_id: int) -> None:
        async with self._sm() as session, session.begin():
            row = await session.get(SkillSourceStatusModel, skill_id)
            if row is not None:
                await session.delete(row)


__all__ = ["SkillSourceStatusModel", "SkillSourceStatusRepo"]
