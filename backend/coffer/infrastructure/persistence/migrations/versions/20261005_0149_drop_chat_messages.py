"""Coffer stops storing conversation text

The text of a conversation lives in the agent's own session, so Coffer keeps
only the conversation *index* (``conversations``) and only for the conversations
a channel owns. This revision drops ``chat_reply_files`` and ``chat_messages``
(with their indexes), drops ``conversations.archived_at`` (and its index), and
deletes the conversation rows no channel owns (``channel_uid IS NULL``: the web
chat's own conversations, whose native sessions remain in the agent).

The retention policies of the two conversation entries (``conversations`` and
``conversations_archive``) are not rows of ``runs.db``: they live in
``local/retention.json`` and are dropped from it at startup, so nothing is
removed here.

``downgrade()`` recreates the empty tables and the (nullable) column exactly as
the baseline defined them. The deleted rows and the dropped messages are NOT
restored.

Revision ID: 0149
Revises: 0148
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0149"
down_revision: str | None = "0148"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_chat_reply_files_message", table_name="chat_reply_files")
    op.drop_table("chat_reply_files")
    op.drop_index("idx_chat_messages_conv", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.execute("DELETE FROM conversations WHERE channel_uid IS NULL")
    op.drop_index("idx_conversations_archived", table_name="conversations")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("archived_at")


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("archived_at", sa.TIMESTAMP(), nullable=True))
    op.create_index("idx_conversations_archived", "conversations", ["archived_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default=sa.text("'complete'"), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_chat_messages_conv_seq"),
    )
    op.create_index("idx_chat_messages_conv", "chat_messages", ["conversation_id", "seq"])

    op.create_table(
        "chat_reply_files",
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Integer(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("diff_omitted", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("message_id", "path"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_chat_reply_files_message", "chat_reply_files", ["message_id", "seq"])
