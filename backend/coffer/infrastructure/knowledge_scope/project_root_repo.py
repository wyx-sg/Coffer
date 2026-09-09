"""Persistence for a project scope's originating git root.

A per-project knowledge scope is keyed by a deterministic ULID derived from its
git-root (``infrastructure/knowledge_scope/scope_fs.project_identity``). That
mapping is one-way: the ULID does not recover the absolute path. This table
records the ``scope_name -> project_root`` mapping captured at provisioning
time so the REST surface can echo the human-readable project root back to the
UI. The global scope and named collections have no project root (``None``).

Pure binding state — the canonical facts live in the unified ``documents``
schema. The ORM model registers against the shared ``Base.metadata`` so Alembic
discovers it via the ``env.py`` import.
"""

from __future__ import annotations

from sqlalchemy import String, delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class KnowledgeScopeProjectRootModel(Base):
    __tablename__ = "knowledge_scope_project_roots"

    scope_name: Mapped[str] = mapped_column(String, primary_key=True)
    project_root: Mapped[str] = mapped_column(String, nullable=False)


class ProjectRootRepo:
    """``scope_name -> project_root`` upsert/lookup over a tiny mapping table."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def set(self, scope_name: str, project_root: str) -> None:
        """Idempotently record a store's originating project root."""
        async with self._sm() as session:
            stmt = (
                sqlite_insert(KnowledgeScopeProjectRootModel)
                .values(scope_name=scope_name, project_root=project_root)
                .on_conflict_do_update(
                    index_elements=[KnowledgeScopeProjectRootModel.scope_name],
                    set_={"project_root": project_root},
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def get(self, scope_name: str) -> str | None:
        async with self._sm() as session:
            stmt = select(KnowledgeScopeProjectRootModel.project_root).where(
                KnowledgeScopeProjectRootModel.scope_name == scope_name
            )
            root: str | None = (await session.execute(stmt)).scalar_one_or_none()
            return root

    async def list_all(self) -> list[tuple[str, str]]:
        """Every ``(scope_name, project_root)`` mapping. Used by store
        consolidation to re-resolve each root and collapse duplicate stores."""
        async with self._sm() as session:
            stmt = select(
                KnowledgeScopeProjectRootModel.scope_name,
                KnowledgeScopeProjectRootModel.project_root,
            )
            return [(name, root) for name, root in (await session.execute(stmt)).all()]

    async def delete(self, scope_name: str) -> None:
        """Drop a scope's project-root row. The generic scope teardown
        (``cleanup_scope``) does not touch this binding table, so retiring a
        scope must call this explicitly to avoid a dangling mapping."""
        async with self._sm() as session:
            await session.execute(
                delete(KnowledgeScopeProjectRootModel).where(
                    KnowledgeScopeProjectRootModel.scope_name == scope_name
                )
            )
            await session.commit()
