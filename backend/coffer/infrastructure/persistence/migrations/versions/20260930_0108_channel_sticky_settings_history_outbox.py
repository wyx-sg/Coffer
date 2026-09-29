"""Channel threads keep their settings, remember their conversations, and owe
the web's replies.

Three additions for spec channels' redesigned commands and spec chat's reply
mirroring:

* ``channel_thread_conversations`` gains ``chat_kind`` (which send path reaches
  the thread) and ``preferred_model`` / ``preferred_effort`` /
  ``preferred_cwd`` — the settings a fresh conversation in the thread opens
  with, beside the existing ``preferred_agent``;
* ``channel_thread_history`` records every conversation a thread opened, which
  `/resume` lists and a web reply is mirrored back through. Each thread's
  current conversation is back-filled, so it can be resumed and mirrored from
  the start; nothing older is known;
* ``channel_outbox`` holds a web reply (and the agent's answer) a channel could
  not send yet.

Revision ID: 0108
Revises: 0107
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0108"
down_revision: str | None = "0107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_THREADS = "channel_thread_conversations"


def upgrade() -> None:
    op.add_column(_THREADS, sa.Column("chat_kind", sa.String(), nullable=True))
    op.add_column(_THREADS, sa.Column("preferred_model", sa.String(), nullable=True))
    op.add_column(_THREADS, sa.Column("preferred_effort", sa.String(), nullable=True))
    op.add_column(_THREADS, sa.Column("preferred_cwd", sa.Text(), nullable=True))
    op.create_table(
        "channel_thread_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False, server_default=""),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("chat_kind", sa.String(), nullable=True),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", name="uq_channel_thread_history_conversation"),
    )
    op.create_index(
        "idx_channel_thread_history_thread",
        "channel_thread_history",
        ["resource_id", "chat_id", "thread_id"],
    )
    op.create_table(
        "channel_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False, server_default=""),
        sa.Column("chat_kind", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_channel_outbox_pending", "channel_outbox", ["resource_id", "delivered_at"])
    op.create_index("idx_channel_outbox_conversation", "channel_outbox", ["conversation_id"])
    # Back-fill: each thread's current conversation is the one piece of history
    # the tables already knew. One statement, so the timestamps stay in the
    # column's own stored form; the first row per conversation wins.
    op.execute(
        sa.text(
            "INSERT INTO channel_thread_history "
            "(resource_id, chat_id, thread_id, conversation_id, chat_kind, opened_at) "
            f"SELECT resource_id, chat_id, thread_id, active_conversation_id, NULL, "
            f"MIN(updated_at) FROM {_THREADS} WHERE active_conversation_id IS NOT NULL "
            "GROUP BY active_conversation_id"
        )
    )


def downgrade() -> None:
    op.drop_index("idx_channel_outbox_conversation", table_name="channel_outbox")
    op.drop_index("idx_channel_outbox_pending", table_name="channel_outbox")
    op.drop_table("channel_outbox")
    op.drop_index("idx_channel_thread_history_thread", table_name="channel_thread_history")
    op.drop_table("channel_thread_history")
    op.drop_column(_THREADS, "preferred_cwd")
    op.drop_column(_THREADS, "preferred_effort")
    op.drop_column(_THREADS, "preferred_model")
    op.drop_column(_THREADS, "chat_kind")
