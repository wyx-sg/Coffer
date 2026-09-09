"""Persistence for a knowledge scope's user-set display label.

A per-project scope is named ``project-<ULID>`` where the ULID derives
(one-way) from the originating git-root. When that root was never recorded
(``knowledge_scope_project_roots`` has no row), the UI has no readable name to
show and falls back to the opaque scope name. This table lets the user attach a
human display label to ANY scope, keyed by scope name, so an unlabelled scope
reads as a name the user chose instead of ``project-<ULID>``.

Pure binding/display state — the canonical scope is the ``knowledge`` Resource; this
mirrors :mod:`coffer.infrastructure.knowledge_scope.project_root_repo`. The ORM model
registers against the shared ``Base.metadata`` so Alembic discovers it via the
``env.py`` import.
"""

from __future__ import annotations

from sqlalchemy import String, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class KnowledgeScopeLabelModel(Base):
    __tablename__ = "knowledge_scope_labels"

    scope_name: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)


class StoreLabelRepo:
    """``scope_name -> label`` upsert / lookup / clear over a tiny mapping table."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def set(self, scope_name: str, label: str) -> None:
        """Idempotently record a store's display label."""
        async with self._sm() as session:
            stmt = (
                sqlite_insert(KnowledgeScopeLabelModel)
                .values(scope_name=scope_name, label=label)
                .on_conflict_do_update(
                    index_elements=[KnowledgeScopeLabelModel.scope_name],
                    set_={"label": label},
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def clear(self, scope_name: str) -> None:
        """Clear a store's label (revert to the derived / fallback name).

        Persists an EMPTY-STRING marker row instead of deleting: sync needs to
        distinguish "cleared here" from "never labelled" so a clear propagates
        instead of resurrecting from the fleet's stale doc (spec 010
        ``memory-labels``). The read surfaces (`get`/`get_many`) hide the
        marker, so every display path still sees "no label"."""
        await self.set(scope_name, "")

    async def get(self, scope_name: str) -> str | None:
        async with self._sm() as session:
            stmt = select(KnowledgeScopeLabelModel.label).where(
                KnowledgeScopeLabelModel.scope_name == scope_name
            )
            label: str | None = (await session.execute(stmt)).scalar_one_or_none()
            return label or None  # the empty-string clear marker reads as absent

    async def list_all(self) -> dict[str, str]:
        """Every ``scope_name -> label`` row INCLUDING empty-string clear
        markers — the sync export surface (markers propagate the clear)."""
        async with self._sm() as session:
            rows = (await session.execute(select(KnowledgeScopeLabelModel))).scalars().all()
            return {row.scope_name: row.label for row in rows}

    async def get_many(self, store_names: list[str]) -> dict[str, str]:
        """Batch lookup so the list endpoint stays one query, not N."""
        if not store_names:
            return {}
        async with self._sm() as session:
            stmt = select(
                KnowledgeScopeLabelModel.scope_name, KnowledgeScopeLabelModel.label
            ).where(KnowledgeScopeLabelModel.scope_name.in_(store_names))
            rows = (await session.execute(stmt)).all()
            return {row[0]: row[1] for row in rows if row[1]}  # markers read as absent
