"""memory kind tables (spec 007-memory)

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-28

Adds the memory_records table for spec 007-memory. Chained after
0007_knowledge_tables (spec 006-knowledge-base).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("store_name", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("store_name", "id", name="pk_memory_records"),
    )
    # Spec lists this index as ``(store_name, created_at DESC)`` because the
    # list endpoint returns newest-first; SQLite 3.3+ honours DESC in index
    # definitions. CODE26-008.
    op.create_index(
        "idx_memory_records_store_time",
        "memory_records",
        ["store_name", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_memory_records_store_time", table_name="memory_records")
    op.drop_table("memory_records")
