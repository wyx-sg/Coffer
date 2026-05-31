"""ORM + repo for the `kb_documents` table (knowledge_base kind).

Per Contract 5 (cross-kind imports forbidden), this module must NOT import
from any other kind module.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    TIMESTAMP,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.domain.knowledge_base.document import Document
from coffer.infrastructure.persistence.base import Base


class KBDocumentModel(Base):
    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String, nullable=False)
    kb_name: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    extension: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("kb_name", "id", name="pk_kb_documents"),
        UniqueConstraint("kb_name", "sha256", name="uq_kb_documents_kb_sha256"),
        Index("idx_kb_documents_kb_time", "kb_name", "ingested_at"),
    )


def _tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_domain(row: KBDocumentModel) -> Document:
    return Document(
        id=row.id,
        kb_name=row.kb_name,
        filename=row.filename,
        extension=row.extension,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        chunk_count=row.chunk_count,
        ingested_at=_tz(row.ingested_at),
    )


class SqlAlchemyKBDocumentRepo:
    """Implements the application-layer `KBDocumentRepo` protocol."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def create(self, d: Document) -> Document:
        async with self._sm() as session:
            row = KBDocumentModel(
                id=d.id,
                kb_name=d.kb_name,
                filename=d.filename,
                extension=d.extension,
                size_bytes=d.size_bytes,
                sha256=d.sha256,
                chunk_count=d.chunk_count,
                ingested_at=d.ingested_at,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _to_domain(row)

    async def list_by_kb(self, kb_name: str, *, limit: int, offset: int) -> list[Document]:
        async with self._sm() as session:
            stmt = (
                select(KBDocumentModel)
                .where(KBDocumentModel.kb_name == kb_name)
                .order_by(KBDocumentModel.ingested_at.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(r) for r in rows]

    async def count_by_kb(self, kb_name: str) -> int:
        async with self._sm() as session:
            stmt = (
                select(func.count())
                .select_from(KBDocumentModel)
                .where(KBDocumentModel.kb_name == kb_name)
            )
            return int((await session.execute(stmt)).scalar_one())

    async def get(self, kb_name: str, document_id: str) -> Document | None:
        async with self._sm() as session:
            stmt = select(KBDocumentModel).where(
                KBDocumentModel.kb_name == kb_name,
                KBDocumentModel.id == document_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return _to_domain(row) if row else None

    async def exists_by_hash(self, kb_name: str, sha256: str) -> bool:
        async with self._sm() as session:
            stmt = select(KBDocumentModel.id).where(
                KBDocumentModel.kb_name == kb_name,
                KBDocumentModel.sha256 == sha256,
            )
            return (await session.execute(stmt)).first() is not None

    async def find_by_hash(self, kb_name: str, sha256: str) -> list[Document]:
        # Backed by the ``uq_kb_documents_kb_sha256`` UniqueConstraint index
        # (CODE22-010 — replaces a paginated 1000-row scan).
        async with self._sm() as session:
            stmt = select(KBDocumentModel).where(
                KBDocumentModel.kb_name == kb_name,
                KBDocumentModel.sha256 == sha256,
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [_to_domain(r) for r in rows]

    async def delete(self, kb_name: str, document_id: str) -> bool:
        async with self._sm() as session:
            stmt = sa_delete(KBDocumentModel).where(
                KBDocumentModel.kb_name == kb_name,
                KBDocumentModel.id == document_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return (result.rowcount or 0) > 0

    async def delete_all(self, kb_name: str) -> int:
        async with self._sm() as session:
            stmt = sa_delete(KBDocumentModel).where(KBDocumentModel.kb_name == kb_name)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount or 0
