"""``scheduled_task_runs`` without a chat

Scheduled tasks no longer run in a chat (ADR automation-is-a-scheduled-prompt,
2026-11-06): the run's ``channel_uid`` and ``chat_id`` go, and the two
outcomes only a chat had — ``replied`` and ``silent`` — read as ``done``.

Revision ID: 0156
Revises: 0155
Create Date: 2026-11-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0156"
down_revision: str | None = "0155"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE scheduled_task_runs SET outcome = 'done' WHERE outcome IN ('replied', 'silent')"
    )
    with op.batch_alter_table("scheduled_task_runs") as batch:
        batch.drop_column("chat_id")
        batch.drop_column("channel_uid")


def downgrade() -> None:
    with op.batch_alter_table("scheduled_task_runs") as batch:
        batch.add_column(sa.Column("channel_uid", sa.String(), nullable=False, server_default=""))
        batch.add_column(sa.Column("chat_id", sa.String(), nullable=False, server_default=""))
