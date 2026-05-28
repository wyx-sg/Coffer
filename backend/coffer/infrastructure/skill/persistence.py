"""Skill-kind ORM models + repos.

Per Contract 5, this module must not import any other kind subpackage.
The `skill_agent_bindings` table FKs reference `resources(id)` for both
skill and agent — the FK is to the kind-agnostic core, not to either
kind-specific module, so the contract is upheld.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.skill.binding import BindingState, LinkMode
from coffer.infrastructure.persistence.base import Base


class SkillAgentBindingModel(Base):
    __tablename__ = "skill_agent_bindings"

    skill_resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_linked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_link_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_mode: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint(
            "skill_resource_id",
            "agent_resource_id",
            name="pk_skill_agent_bindings",
        ),
        Index("idx_bindings_agent", "agent_resource_id", "enabled"),
        Index("idx_bindings_skill", "skill_resource_id", "enabled"),
    )


def _tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _row_to_domain(row: SkillAgentBindingModel) -> BindingState:
    return BindingState(
        skill_resource_id=row.skill_resource_id,
        agent_resource_id=row.agent_resource_id,
        enabled=row.enabled,
        last_linked_at=_tz(row.last_linked_at),
        last_link_path=row.last_link_path,
        link_mode=LinkMode(row.link_mode) if row.link_mode else None,
    )


class SkillBindingRepo:
    """CRUD for `skill_agent_bindings`."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def find(self, skill_id: int, agent_id: int) -> BindingState | None:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(
                SkillAgentBindingModel.skill_resource_id == skill_id,
                SkillAgentBindingModel.agent_resource_id == agent_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _row_to_domain(row) if row else None

    async def list_for_skill(self, skill_id: int) -> list[BindingState]:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(
                SkillAgentBindingModel.skill_resource_id == skill_id
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_row_to_domain(r) for r in rows]

    async def list_for_agent(self, agent_id: int) -> list[BindingState]:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(
                SkillAgentBindingModel.agent_resource_id == agent_id
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_row_to_domain(r) for r in rows]

    async def list_enabled(self) -> list[BindingState]:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(SkillAgentBindingModel.enabled.is_(True))
            rows = (await session.execute(stmt)).scalars().all()
            return [_row_to_domain(r) for r in rows]

    async def list_all(self) -> list[BindingState]:
        """One-shot read of every binding row.

        Surfaces use this to build a ``skill_id -> [bindings]`` map in
        memory and avoid issuing one query per skill in list endpoints
        (an N+1 pattern in /api/v1/skills).
        """
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel)
            rows = (await session.execute(stmt)).scalars().all()
            return [_row_to_domain(r) for r in rows]

    async def upsert(
        self,
        *,
        skill_id: int,
        agent_id: int,
        enabled: bool,
        last_linked_at: datetime | None = None,
        last_link_path: str | None = None,
        link_mode: LinkMode | None = None,
    ) -> BindingState:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(
                SkillAgentBindingModel.skill_resource_id == skill_id,
                SkillAgentBindingModel.agent_resource_id == agent_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = SkillAgentBindingModel(
                    skill_resource_id=skill_id,
                    agent_resource_id=agent_id,
                    enabled=enabled,
                    last_linked_at=last_linked_at,
                    last_link_path=last_link_path,
                    link_mode=link_mode.value if link_mode else None,
                )
                session.add(row)
            else:
                # Always overwrite — including writing ``None`` to clear
                # ``last_link_path`` / ``link_mode`` on disable. A previous
                # ``if x is not None: row.x = x`` guard left stale paths
                # behind on the row after disable, which then leaked into
                # verify drift output as phantom "missing link" entries.
                row.enabled = enabled
                row.last_linked_at = last_linked_at
                row.last_link_path = last_link_path
                row.link_mode = link_mode.value if link_mode else None
            await session.commit()
            await session.refresh(row)
            return _row_to_domain(row)

    async def delete(self, skill_id: int, agent_id: int) -> None:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(
                SkillAgentBindingModel.skill_resource_id == skill_id,
                SkillAgentBindingModel.agent_resource_id == agent_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def delete_for_skill(self, skill_id: int) -> int:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(
                SkillAgentBindingModel.skill_resource_id == skill_id
            )
            rows = (await session.execute(stmt)).scalars().all()
            for r in rows:
                await session.delete(r)
            await session.commit()
            return len(rows)

    async def delete_for_agent(self, agent_id: int) -> int:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(
                SkillAgentBindingModel.agent_resource_id == agent_id
            )
            rows = (await session.execute(stmt)).scalars().all()
            for r in rows:
                await session.delete(r)
            await session.commit()
            return len(rows)
