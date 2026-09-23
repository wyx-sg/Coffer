"""keep every converge round, not only the last one

``sync_remotes.last_*`` answers "what happened just now". It cannot answer
"what has been happening", and that is the question a user actually brings to
the Sync page: a round that failed once is noise, a round that has failed every
hour since Tuesday is the answer, and a vault that has quietly published
nothing for a week looks identical to a healthy one through a single row.

So every round is appended here as well. The remote's ``last_*`` columns stay
exactly as they are — denormalised so a status surface reads the current state
without touching the history — and both writes happen in one transaction, so
the newest row here and those columns can never describe different rounds.

Machine-local, like the pointer: ``coffer.db`` is excluded from the bundle
(spec vault-sync "Keep reach machine-local"), and a history that travelled would
be another machine's account of rounds this one never ran.

Nothing is backfilled. The one round the remote row already holds is the round
the next write records anyway, and inventing a history row for it would date it
to this migration rather than to when it ran.

Revision ID: 0075
Revises: 0074
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0075"
down_revision: str | None = "0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("join_kind", sa.String(), nullable=True),
        # ``commit`` is reserved in SQL; the column says what it holds instead.
        sa.Column("commit_sha", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
    )
    # Read newest-first, pruned oldest-first — both are this index.
    op.create_index("ix_sync_runs_finished_at", "sync_runs", ["finished_at"])


def downgrade() -> None:
    """Drop the history.

    Not preserved anywhere on the way down, and it should not be: a build below
    this revision has nowhere to put it and no surface that reads it. The
    remote's ``last_*`` columns survive untouched, so the status page a
    downgraded build shows is exactly as complete as it was before.
    """
    op.drop_index("ix_sync_runs_finished_at", table_name="sync_runs")
    op.drop_table("sync_runs")
