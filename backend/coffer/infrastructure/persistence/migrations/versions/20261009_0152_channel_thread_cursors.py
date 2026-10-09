"""add ``channel_thread_cursors``

How far each conversation has seen each platform thread, so a thread turn folds
only the messages posted since that conversation's previous turn there (spec
channels "Ground a thread turn in a bounded slice of the thread"; change
fetch-thread-history-on-demand). Ids and times only.

Revision ID: 0152
Revises: 0151
Create Date: 2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0152"
down_revision: str | None = "0151"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_thread_cursors",
        sa.Column("resource_uid", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("last_message_id", sa.String(), nullable=False),
        sa.Column("last_message_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("resource_uid", "chat_id", "thread_id", "conversation_id"),
    )


def downgrade() -> None:
    op.drop_table("channel_thread_cursors")
