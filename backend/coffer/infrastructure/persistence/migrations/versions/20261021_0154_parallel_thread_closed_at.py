"""add ``channel_thread_conversations.parallel_closed_at``

A parallel thread a direct chat opened with `/thread` can now be closed — by
`/close` inside it, or by the sweep once it has sat idle (spec channels "Open
parallel conversations beside a direct chat"). The row stays, so the thread's
number is never given out again; this column says it is closed. Nullable: open
threads and every other row have none.

Revision ID: 0154
Revises: 0153
Create Date: 2026-10-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0154"
down_revision: str | None = "0153"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("channel_thread_conversations") as batch:
        batch.add_column(
            sa.Column("parallel_closed_at", sa.TIMESTAMP(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("channel_thread_conversations") as batch:
        batch.drop_column("parallel_closed_at")
