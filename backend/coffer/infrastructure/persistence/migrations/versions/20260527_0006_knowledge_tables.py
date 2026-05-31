"""knowledge_base kind tables (spec 006-knowledge-base)

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-27

Chains after 0005_skill_tables (spec 005-skill-manager). The memory_records
table is introduced separately by 0007_memory_tables (spec 007-memory).
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
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kb_name", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("extension", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("ingested_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("kb_name", "id", name="pk_kb_documents"),
        sa.UniqueConstraint("kb_name", "sha256", name="uq_kb_documents_kb_sha256"),
    )
    op.create_index(
        "idx_kb_documents_kb_time",
        "kb_documents",
        ["kb_name", "ingested_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_kb_documents_kb_time", table_name="kb_documents")
    op.drop_table("kb_documents")
