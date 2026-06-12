"""conversations.archived_at (spec 008 — archive/restore)

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL = active; a timestamp = archived at that instant. Indexed because the
    # default conversation list filters on archived_at IS NULL.
    op.add_column(
        "conversations",
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_conversations_archived", "conversations", ["archived_at"])


def downgrade() -> None:
    op.drop_index("idx_conversations_archived", table_name="conversations")
    op.drop_column("conversations", "archived_at")
