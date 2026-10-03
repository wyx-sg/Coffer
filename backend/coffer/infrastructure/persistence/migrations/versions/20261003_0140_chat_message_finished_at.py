"""add ``chat_messages.finished_at``

When an assistant reply ended (complete, stopped or failed), so a conversation
can show how long a reply took. Null while a reply streams, on user messages,
and on rows written before this column existed — their duration is unknown.

The downgrade drops the column.

Revision ID: 0140
Revises: 0139
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0140"
down_revision: str | None = "0139"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "chat_messages" not in inspector.get_table_names():
        return
    if "finished_at" in {c["name"] for c in inspector.get_columns("chat_messages")}:
        return
    op.add_column("chat_messages", sa.Column("finished_at", sa.TIMESTAMP(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_column("finished_at")
