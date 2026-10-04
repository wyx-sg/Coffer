"""add ``chat_reply_files``

What each assistant reply changed in each file it wrote: its added and removed
line counts and the unified diff (spec chat "Record what each reply changed in
each file"). One row per file per reply, deleted with the reply
(``ON DELETE CASCADE``; the engine runs with ``PRAGMA foreign_keys = ON``).
Replies written before this table existed have no rows.

The downgrade drops the table.

Revision ID: 0142
Revises: 0141
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0142"
down_revision: str | None = "0141"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "chat_messages" not in tables or "chat_reply_files" in tables:
        return
    op.create_table(
        "chat_reply_files",
        sa.Column(
            "message_id",
            sa.String(),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("path", sa.String(), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Integer(), nullable=False),
        sa.Column("diff", sa.Text()),
        sa.Column("diff_omitted", sa.String()),
    )
    op.create_index("idx_chat_reply_files_message", "chat_reply_files", ["message_id", "seq"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "chat_reply_files" in inspector.get_table_names():
        op.drop_index("idx_chat_reply_files_message", table_name="chat_reply_files")
        op.drop_table("chat_reply_files")
