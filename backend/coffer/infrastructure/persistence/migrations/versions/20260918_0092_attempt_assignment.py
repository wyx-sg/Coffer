"""An attempt says who is to run it, on which model, thinking how hard.

A task's agent was the template's and only the template's, and its model and
reasoning effort were nobody's — they were whatever the agent's own
configuration happened to project. The picker that changes them lives on a
conversation, and a task has no conversation until it starts, so the one moment
a developer most wants to say "do this one on the bigger model" — before it
runs — was the one moment nothing could be said (spec workflow, FR-071).

These three columns are that answer, per ATTEMPT rather than per task: a retry
is a new attempt (FR-022), so choosing a stronger model for the second try
leaves the first attempt's record saying what it actually ran on. NULL means
"whatever the template said", and the template says NULL for "whatever the
agent's own configuration projects" — one ladder, no magic strings.

Nullable with no backfill: an attempt that ran before this column existed ran
on the template's answer, which is exactly what NULL says.

Revision ID: 0092
Revises: 0091
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None

_TABLE = "workflow_node_attempts"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("agent", sa.String(), nullable=True))
    op.add_column(_TABLE, sa.Column("model", sa.String(), nullable=True))
    op.add_column(_TABLE, sa.Column("effort", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "effort")
    op.drop_column(_TABLE, "model")
    op.drop_column(_TABLE, "agent")
