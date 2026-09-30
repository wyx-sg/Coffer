"""Skill delivery bindings, in ``derived/derived.db``.

Which skill copies are delivered into which agent is an observation of this
machine's disk that the ``skill_link`` pass makes again, so the table is
derived (``coffer.infrastructure.persistence.derived_db``), keyed by the
skill's and the agent's uids. A resource's deletion does not cascade into it
(there is no resource table to cascade from): the skill and agent kinds
remove their rows in their own delete hooks, as they always did first.

Per Contract 5, this module must not import any other kind subpackage.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.skill.binding import BindingState, LinkMode
from coffer.infrastructure.persistence.derived_db import SkillAgentBindingModel


def _tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _row_to_domain(row: SkillAgentBindingModel) -> BindingState:
    return BindingState(
        skill_uid=row.skill_uid,
        agent_uid=row.agent_uid,
        enabled=row.enabled,
        last_linked_at=_tz(row.last_linked_at),
        last_link_path=row.last_link_path,
        link_mode=LinkMode(row.link_mode) if row.link_mode else None,
    )


class SkillBindingRepo:
    """CRUD for the derived `skill_agent_bindings` table."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def find(self, skill_uid: str, agent_uid: str) -> BindingState | None:
        async with self._sm() as session:
            row = await session.get(SkillAgentBindingModel, (skill_uid, agent_uid))
            return _row_to_domain(row) if row else None

    async def _where(self, *clauses: object) -> list[BindingState]:
        async with self._sm() as session:
            stmt = select(SkillAgentBindingModel).where(*clauses)  # type: ignore[arg-type]
            rows = (await session.execute(stmt)).scalars().all()
            return [_row_to_domain(r) for r in rows]

    async def list_for_skill(self, skill_uid: str) -> list[BindingState]:
        return await self._where(SkillAgentBindingModel.skill_uid == skill_uid)

    async def list_for_agent(self, agent_uid: str) -> list[BindingState]:
        return await self._where(SkillAgentBindingModel.agent_uid == agent_uid)

    async def list_enabled(self) -> list[BindingState]:
        return await self._where(SkillAgentBindingModel.enabled.is_(True))

    async def list_all(self) -> list[BindingState]:
        """One-shot read of every binding row, so a list endpoint builds its
        ``skill_uid -> [bindings]`` map without one query per skill."""
        return await self._where()

    async def upsert(
        self,
        *,
        skill_uid: str,
        agent_uid: str,
        enabled: bool,
        last_linked_at: datetime | None = None,
        last_link_path: str | None = None,
        link_mode: LinkMode | None = None,
    ) -> BindingState:
        async with self._sm() as session:
            row = await session.get(SkillAgentBindingModel, (skill_uid, agent_uid))
            if row is None:
                row = SkillAgentBindingModel(skill_uid=skill_uid, agent_uid=agent_uid)
                session.add(row)
            # Always overwrite — including writing ``None`` to clear
            # ``last_link_path`` / ``link_mode`` on disable, so a disabled
            # binding never reports a stale path as a missing link.
            row.enabled = enabled
            row.last_linked_at = last_linked_at
            row.last_link_path = last_link_path
            row.link_mode = link_mode.value if link_mode else None
            await session.commit()
            await session.refresh(row)
            return _row_to_domain(row)

    async def delete(self, skill_uid: str, agent_uid: str) -> None:
        async with self._sm() as session:
            await session.execute(
                delete(SkillAgentBindingModel).where(
                    SkillAgentBindingModel.skill_uid == skill_uid,
                    SkillAgentBindingModel.agent_uid == agent_uid,
                )
            )
            await session.commit()

    async def _delete_where(self, *clauses: object) -> int:
        async with self._sm() as session:
            result = await session.execute(
                delete(SkillAgentBindingModel).where(*clauses)  # type: ignore[arg-type]
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def delete_for_skill(self, skill_uid: str) -> int:
        return await self._delete_where(SkillAgentBindingModel.skill_uid == skill_uid)

    async def delete_for_agent(self, agent_uid: str) -> int:
        return await self._delete_where(SkillAgentBindingModel.agent_uid == agent_uid)


__all__ = ["SkillBindingRepo"]
