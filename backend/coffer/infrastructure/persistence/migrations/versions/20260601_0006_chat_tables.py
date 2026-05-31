"""chat tables — conversations + messages (spec 008-builtin-agent-chat)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-01

Adds the conversation/message tables backing the chat surface. The
``builtin_agent`` kind reuses the existing ``resources`` table (no new table),
so only these two are added here.

NOTE: this branch was cut from main at 0005. Specs 006/007 also branch from
near there; when 008 is rebased onto a main that already carries their
migrations, renumber this revision + down_revision to chain after the then-head
(routine multi-feature Alembic reconciliation).
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
        "conversations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("target_ref", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("model_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index(
        "idx_conversations_status_updated",
        "conversations",
        ["status", "updated_at"],
    )
    op.create_table(
        "messages",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mid", sa.String(), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("tool_calls_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("seq", name="pk_messages"),
        sa.UniqueConstraint("mid", name="uq_messages_mid"),
    )
    op.create_index(
        "idx_messages_conversation_seq",
        "messages",
        ["conversation_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index("idx_messages_conversation_seq", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_conversations_status_updated", table_name="conversations")
    op.drop_table("conversations")
