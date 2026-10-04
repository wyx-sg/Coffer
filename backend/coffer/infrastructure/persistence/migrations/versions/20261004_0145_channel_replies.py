"""add ``channel_replies``

Which platform messages make up each bot reply, so the owner can withdraw a
reply later with ``/del`` or the 🗑 button (spec channels "Withdraw a bot reply
on the owner's command"). One row per reply: the channel's uid, the chat and
thread it went to, a JSON list of the platform message ids it was delivered as
(a long reply is several, and so are its files) and when it was sent. No text
is stored. Rows older than the longest platform window are pruned as new ones
are written.

The downgrade drops the table.

Revision ID: 0145
Revises: 0144
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0145"
down_revision: str | None = "0144"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "channel_replies" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "channel_replies",
        sa.Column("reply_id", sa.String(), primary_key=True),
        sa.Column("resource_uid", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False, server_default=""),
        sa.Column("chat_kind", sa.String(), nullable=False),
        sa.Column("message_ids", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_channel_replies_chat", "channel_replies", ["resource_uid", "chat_id", "sent_at"]
    )


def downgrade() -> None:
    if "channel_replies" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("idx_channel_replies_chat", table_name="channel_replies")
        op.drop_table("channel_replies")
