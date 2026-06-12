"""repair: ensure the unified knowledge schema exists (specs 006 + 007)

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-12

The redesign rewrote 0006/0007 IN PLACE: 0006 now creates the unified
``documents``/``chunks``/``documents_fts`` schema and 0007 became a no-op. A DB
that had already applied the PRE-redesign 0006/0007 (which created the legacy
``kb_documents``/``memory_records`` tables) is stamped at 0007, so Alembic never
re-runs the rewritten 0006 — the unified tables are missing and every KB/memory
write fails with "no such table: documents" (reproduced on a real install).

This revision converges both worlds idempotently: every statement is
``IF (NOT) EXISTS``, so a fresh DB (where 0006 already built the schema) is a
no-op and a legacy-stamped DB gets the unified schema created and the legacy
tables dropped (FR-019: legacy data is abandoned, files are the source of
truth — ``reindex`` rebuilds all SQLite state from the markdown files).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kb_documents")
    op.execute("DROP TABLE IF EXISTS memory_records")

    # Mirrors 0006's schema exactly, but tolerant of it already existing.
    op.execute(
        "CREATE TABLE IF NOT EXISTS documents ("
        "id VARCHAR NOT NULL, "
        "kind VARCHAR NOT NULL, "
        "resource_name VARCHAR NOT NULL, "
        "project_id VARCHAR NOT NULL, "
        "path VARCHAR NOT NULL, "
        "title VARCHAR NOT NULL, "
        "description TEXT, "
        "metadata TEXT NOT NULL DEFAULT '{}', "
        "content_sha256 VARCHAR NOT NULL, "
        "source_mode VARCHAR NOT NULL, "
        "created_at TIMESTAMP NOT NULL, "
        "updated_at TIMESTAMP NOT NULL, "
        "CONSTRAINT pk_documents PRIMARY KEY (kind, resource_name, id)"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_kind_res_time "
        "ON documents (kind, resource_name, updated_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_documents_project ON documents (project_id)")

    op.execute(
        "CREATE TABLE IF NOT EXISTS chunks ("
        "id VARCHAR NOT NULL, "
        "document_id VARCHAR NOT NULL, "
        "kind VARCHAR NOT NULL, "
        "resource_name VARCHAR NOT NULL, "
        "position INTEGER NOT NULL, "
        "CONSTRAINT pk_chunks PRIMARY KEY (id)"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks (document_id)")

    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5("
        "text, resource_name UNINDEXED, chunk_id UNINDEXED, "
        "tokenize='unicode61'"
        ")"
    )


def downgrade() -> None:
    # Nothing to reverse: a repair that converges schema state has no inverse;
    # 0006's downgrade owns dropping the unified tables.
    pass
