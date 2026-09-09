"""Persistence for a memory store's user-set display label (spec 007 FR-017c).

A per-project memory store is named ``project-<ULID>`` where the ULID derives
(one-way) from the originating git-root. When that root was never recorded
(``memory_store_project_roots`` has no row), the UI has no readable name to show
and falls back to the opaque store name. This table lets the user attach a human
display label to ANY store, keyed by store name, so an unlabelled store reads as
a name the user chose instead of ``project-<ULID>``.

Pure binding/display state — the canonical store is the ``memory`` Resource; this
mirrors :mod:`coffer.infrastructure.memory.project_root_repo`. The ORM model
registers against the shared ``Base.metadata`` so Alembic discovers it via the
``env.py`` import.
"""

from __future__ import annotations

from sqlalchemy import String, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class MemoryStoreLabelModel(Base):
    __tablename__ = "memory_store_labels"

    store_name: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)


class StoreLabelRepo:
    """``store_name -> label`` upsert / lookup / clear over a tiny mapping table."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def set(self, store_name: str, label: str) -> None:
        """Idempotently record a store's display label."""
        async with self._sm() as session:
            stmt = (
                sqlite_insert(MemoryStoreLabelModel)
                .values(store_name=store_name, label=label)
                .on_conflict_do_update(
                    index_elements=[MemoryStoreLabelModel.store_name],
                    set_={"label": label},
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def clear(self, store_name: str) -> None:
        """Clear a store's label (revert to the derived / fallback name).

        Persists an EMPTY-STRING marker row instead of deleting: sync needs to
        distinguish "cleared here" from "never labelled" so a clear propagates
        instead of resurrecting from the fleet's stale doc (spec 010
        ``memory-labels``). The read surfaces (`get`/`get_many`) hide the
        marker, so every display path still sees "no label"."""
        await self.set(store_name, "")

    async def get(self, store_name: str) -> str | None:
        async with self._sm() as session:
            stmt = select(MemoryStoreLabelModel.label).where(
                MemoryStoreLabelModel.store_name == store_name
            )
            label: str | None = (await session.execute(stmt)).scalar_one_or_none()
            return label or None  # the empty-string clear marker reads as absent

    async def list_all(self) -> dict[str, str]:
        """Every ``store_name -> label`` row INCLUDING empty-string clear
        markers — the sync export surface (markers propagate the clear)."""
        async with self._sm() as session:
            rows = (await session.execute(select(MemoryStoreLabelModel))).scalars().all()
            return {row.store_name: row.label for row in rows}

    async def get_many(self, store_names: list[str]) -> dict[str, str]:
        """Batch lookup so the list endpoint stays one query, not N."""
        if not store_names:
            return {}
        async with self._sm() as session:
            stmt = select(MemoryStoreLabelModel.store_name, MemoryStoreLabelModel.label).where(
                MemoryStoreLabelModel.store_name.in_(store_names)
            )
            rows = (await session.execute(stmt)).all()
            return {row[0]: row[1] for row in rows if row[1]}  # markers read as absent
