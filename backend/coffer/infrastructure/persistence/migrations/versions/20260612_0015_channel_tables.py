"""channel_peers table (spec 009)

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-12

The paired owner of a messaging channel and its active-conversation pointer.
Keyed by ``(resource_id, chat_id)`` so future group chats are new rows, not a
schema change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_peers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False, server_default=""),
        sa.Column("paired_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("active_conversation_id", sa.String(), nullable=True),
        sa.UniqueConstraint("resource_id", "chat_id", name="uq_channel_peers_resource_chat"),
    )
    op.create_index("idx_channel_peers_resource", "channel_peers", ["resource_id"])


def downgrade() -> None:
    op.drop_index("idx_channel_peers_resource", table_name="channel_peers")
    op.drop_table("channel_peers")
