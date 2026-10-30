"""add ``scheduled_task_runs``

Every run of a scheduled task — a follow-up an agent booked, the daily report,
a task the owner set up — with when it was due, when it ran and how it ended
(spec channels "Keep every scheduled run in the task's history"; change
add-scheduled-tasks). Ids, times and outcomes only.

Revision ID: 0155
Revises: 0154
Create Date: 2026-10-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0155"
down_revision: str | None = "0154"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_task_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("task_uid", sa.String(), nullable=False),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("channel_uid", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("due_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("catch_up", sa.Boolean(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "idx_scheduled_task_runs_task", "scheduled_task_runs", ["task_uid", "started_at"]
    )
    op.create_index("idx_scheduled_task_runs_started", "scheduled_task_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("idx_scheduled_task_runs_started", table_name="scheduled_task_runs")
    op.drop_index("idx_scheduled_task_runs_task", table_name="scheduled_task_runs")
    op.drop_table("scheduled_task_runs")
