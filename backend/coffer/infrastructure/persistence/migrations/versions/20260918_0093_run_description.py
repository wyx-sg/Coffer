"""A run carries a description of its own.

A run was created with a title and nothing else, and neither could be changed
afterwards. The title is the only thing that distinguishes one delivery from
the next in a list of forty, and it is typed at the moment the developer knows
least about the work — before the first task has opened. A label you cannot
correct is a list you stop reading.

So the run gains a ``description`` and both become editable (spec workflow,
FR-070). Neither is part of the projection: the run's status, its stage and its
position are folded from ``workflow_events`` and only the engine writes them.
A title is a label the person put on the work, which is why this column sits
outside the optimistic-lock cycle exactly as ``inputs`` does.

Nullable with no backfill: a run created before this had no description, and
``NULL`` says that rather than inventing one.

Revision ID: 0093
Revises: 0092
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("workflow_runs", "description")
