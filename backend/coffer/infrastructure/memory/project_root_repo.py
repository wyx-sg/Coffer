"""Persistence for a memory store's originating project root (spec 007).

A per-project memory store is keyed by a deterministic ULID derived from its
git-root (``infrastructure/memory/scope_fs.project_ulid``). That mapping is
one-way: the ULID does not recover the absolute path. This table records the
``store_name -> project_root`` mapping captured at provisioning time so the
REST surface can echo the human-readable project root back to the UI
(finding #10). The global store has no project root (it returns ``None``).

Pure binding state — the canonical facts live in the unified ``documents``
schema. The ORM model registers against the shared ``Base.metadata`` so Alembic
discovers it via the ``env.py`` import.
"""

from __future__ import annotations

from sqlalchemy import String, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class MemoryStoreProjectRootModel(Base):
    __tablename__ = "memory_store_project_roots"

    store_name: Mapped[str] = mapped_column(String, primary_key=True)
    project_root: Mapped[str] = mapped_column(String, nullable=False)


class ProjectRootRepo:
    """``store_name -> project_root`` upsert/lookup over a tiny mapping table."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def set(self, store_name: str, project_root: str) -> None:
        """Idempotently record a store's originating project root."""
        async with self._sm() as session:
            stmt = (
                sqlite_insert(MemoryStoreProjectRootModel)
                .values(store_name=store_name, project_root=project_root)
                .on_conflict_do_update(
                    index_elements=[MemoryStoreProjectRootModel.store_name],
                    set_={"project_root": project_root},
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get(self, store_name: str) -> str | None:
        async with self._sm() as session:
            stmt = select(MemoryStoreProjectRootModel.project_root).where(
                MemoryStoreProjectRootModel.store_name == store_name
            )
            root: str | None = (await session.execute(stmt)).scalar_one_or_none()
            return root
