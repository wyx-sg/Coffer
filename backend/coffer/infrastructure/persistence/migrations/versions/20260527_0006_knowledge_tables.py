"""unified knowledge substrate tables (specs 006-knowledge-base + 007-memory)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-09

Redesign: replaces the old per-kind ``kb_documents`` table with the unified
``documents`` + ``chunks`` schema shared by the knowledge_base and memory kinds
(discriminated by ``kind``), plus the FTS5 keyword index ``documents_fts``. The
``vec_chunks`` (sqlite-vec) virtual table is created lazily per store at the
configured embedding width, so it is not part of this migration.

This branch is **unreleased**, so there is no data migration: the migration
simply drops any legacy tables (defensively) and creates the new schema.

Chains after 0005_skill_tables. ``0007_memory_tables`` is now a no-op because
the memory face reuses these same tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Defensive: legacy tables never existed in a released DB, but drop them if
    # an in-progress branch DB carries them.
    op.execute("DROP TABLE IF EXISTS kb_documents")
    op.execute("DROP TABLE IF EXISTS memory_records")

    op.create_table(
        "documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("resource_name", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("content_sha256", sa.String(), nullable=False),
        sa.Column("source_mode", sa.String(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("kind", "resource_name", "id", name="pk_documents"),
    )
    op.create_index(
        "idx_documents_kind_res_time",
        "documents",
        ["kind", "resource_name", sa.text("updated_at DESC")],
    )
    op.create_index("idx_documents_project", "documents", ["project_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("resource_name", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
    )
    op.create_index("idx_chunks_document", "chunks", ["document_id"])

    # FTS5 keyword index. The chunk text lives once inside the FTS index (not
    # duplicated into a base table). ``chunk_id`` UNINDEXED maps a hit back to
    # its chunks row; ``resource_name`` UNINDEXED scopes a search.
    op.execute(
        "CREATE VIRTUAL TABLE documents_fts USING fts5("
        "text, resource_name UNINDEXED, chunk_id UNINDEXED, "
        "tokenize='unicode61'"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS documents_fts")
    op.drop_index("idx_chunks_document", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("idx_documents_project", table_name="documents")
    op.drop_index("idx_documents_kind_res_time", table_name="documents")
    op.drop_table("documents")
