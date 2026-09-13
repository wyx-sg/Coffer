"""The ``memory_overrides`` table — the one thing this layer keeps in a database.

Everything else the memory layer holds is derived from the agents' own memories
and can be thrown away and rebuilt. The developer's decisions about their facts
cannot, so they live here, keyed by an identity that survives a rebuild
(spec memory FR-040, FR-041, FR-070).

A repository, in ``infrastructure/persistence/`` with the others and injected
into the application, because that is where every other repository in this
codebase lives. An earlier draft put it in ``application/memory/`` behind an
import-linter exception; there was no reason for the exception beyond the
repository being small, and small is not an argument for crossing a layer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.memory.overrides import Override
from coffer.infrastructure.persistence.models import MemoryOverrideModel


class OverrideRepository:
    """Reads and writes ``memory_overrides`` — the one table this layer adds.

    Same session style as the rest of the persistence layer: an injected
    ``async_sessionmaker``, one short-lived session per call (see
    ``infrastructure/persistence/sync_remote_repo.py``, which this mirrors).
    """

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def all(self) -> dict[str, Override]:
        async with self._sm() as session:
            rows = (await session.execute(select(MemoryOverrideModel))).scalars().all()
            return {row.fact_key: _to_override(row) for row in rows}

    async def get(self, fact_key: str) -> Override | None:
        async with self._sm() as session:
            row = await session.get(MemoryOverrideModel, fact_key)
            return _to_override(row) if row is not None else None

    async def set(self, override: Override, *, actor: str) -> None:
        """Upsert by ``fact_key`` — setting an override twice replaces it
        rather than erroring on the primary key, so re-recording the same
        decision (or correcting it) needs no separate "does one exist" call.
        """
        async with self._sm() as session:
            values = {
                "fact_key": override.fact_key,
                "hidden": override.hidden,
                "pinned": override.pinned,
                "superseded_by": override.superseded_by,
                "conflict_choice": override.conflict_choice,
                "actor": actor,
                "updated_at": datetime.now(tz=UTC),
            }
            stmt = (
                sqlite_insert(MemoryOverrideModel)
                .values(**values)
                .on_conflict_do_update(index_elements=["fact_key"], set_=values)
            )
            await session.execute(stmt)
            await session.commit()

    async def clear(self, fact_key: str) -> None:
        async with self._sm() as session:
            row = await session.get(MemoryOverrideModel, fact_key)
            if row is not None:
                await session.delete(row)
                await session.commit()


def _to_override(row: MemoryOverrideModel) -> Override:
    return Override(
        fact_key=row.fact_key,
        hidden=row.hidden,
        pinned=row.pinned,
        superseded_by=row.superseded_by,
        conflict_choice=row.conflict_choice,
    )
