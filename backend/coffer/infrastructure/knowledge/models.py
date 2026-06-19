"""SQLAlchemy ORM for the unified ``documents`` + ``chunks`` tables.

Shared by the KB and memory kinds, discriminated by ``kind``. Registered on the
shared ``Base.metadata`` so Alembic + ``create_all`` find them. The chunk text
itself is NOT stored here — it lives in ``documents_fts`` (FTS5 contentless) and
on disk. The FTS5 + sqlite-vec virtual tables are created by the migration, not
by ORM models.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class DocumentModel(Base):
    """One Markdown file = one row. Composite PK ``(kind, resource_name, id)``
    keeps the unified table unambiguous across faces/resources (ids are now
    globally-unique ULIDs — ADR-028 — so a bare id would already be unique)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    resource_name: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}")
    content_sha256: Mapped[str] = mapped_column(String, nullable=False)
    source_mode: Mapped[str] = mapped_column(String, nullable=False)
    # Co-management lock (ADR-028): a locked document refuses every mutation.
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Recoverable soft-delete (ADR-030): NULL = live; set = in trash. Live reads
    # filter deleted_at IS NULL. Memory never sets it.
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("kind", "resource_name", "id", name="pk_documents"),
        Index("idx_documents_kind_res_time", "kind", "resource_name", "updated_at"),
        Index("idx_documents_project", "project_id"),
    )


class ChunkModel(Base):
    """One chunk per row. ``id`` is ``'<store-scope>:<doc-id>:<position>'``
    (``store_scope`` digests ``(kind, resource_name)`` so the same
    content-addressed doc id in two stores never collides); the text lives in
    ``documents_fts`` keyed by FTS rowid, not here."""

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    resource_name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("idx_chunks_document", "document_id"),)
