"""channel_thread_conversations: per-thread conversation identity (spec 009 FR-032)

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-08

Conversation identity moves from the peer row (keyed ``(resource_id, chat_id)``)
to a per-thread binding keyed ``(resource_id, chat_id, thread_id)``. A DM (or a
group's main chat) is ``thread_id=""``; each thread in a group is its own row
with its own active conversation and its own sticky agent — so concurrent turns
in different threads never collide on one conversation ("a turn is already
running"), and one bot can run different agents in different threads (FR-040).

Pairing/owner identity stays on ``channel_peers``. Every existing peer's active
conversation + sticky agent are backfilled into the new table as its
``thread_id=""`` row, so no active DM (or group-main) conversation is lost.

Idempotent on a DB that already has the table (the roundtrip suite stamps back
and replays the chain tail). Reversible (drops the table).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("channel_thread_conversations"):
        return
    op.create_table(
        "channel_thread_conversations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False, server_default=""),
        sa.Column("active_conversation_id", sa.String(), nullable=True),
        sa.Column("preferred_agent", sa.String(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "resource_id",
            "chat_id",
            "thread_id",
            name="uq_channel_thread_conv_resource_chat_thread",
        ),
    )
    op.create_index(
        "idx_channel_thread_conv_resource",
        "channel_thread_conversations",
        ["resource_id"],
    )

    # Backfill: every existing peer becomes its own ``thread_id=""`` binding,
    # carrying the conversation it was driving and its sticky agent so an
    # in-flight DM (or group-main) conversation survives the model change.
    op.execute(
        """
        INSERT INTO channel_thread_conversations
            (resource_id, chat_id, thread_id, active_conversation_id,
             preferred_agent, updated_at)
        SELECT resource_id, chat_id, '', active_conversation_id,
               preferred_agent, paired_at
        FROM channel_peers
        """
    )


def downgrade() -> None:
    if not _has_table("channel_thread_conversations"):
        return
    op.drop_index(
        "idx_channel_thread_conv_resource",
        table_name="channel_thread_conversations",
    )
    op.drop_table("channel_thread_conversations")
