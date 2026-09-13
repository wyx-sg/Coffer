"""this machine's convergence state, and a sync remote that records rounds

Bidirectional convergence needs one thing the one-way backup never did: a
record of what this vault has **provably absorbed**. That is the pointer, and
with it the paths this vault could not absorb — the retry and not-applicable
sets the exporter must leave in the working tree, or a failure to apply turns
into a published deletion.

All three are machine-local and MUST NEVER sync (spec vault-sync ``## What does
not sync``). SQLite is where they belong precisely because ``coffer.db`` is
already excluded from the bundle: a pointer that travelled would be another
machine's claim about what this vault holds, and the diff-based apply rests on
it being this machine's own.

``sync_remotes`` keeps its configuration columns untouched — the URL, branch,
credential reference and interval a user typed mean the same thing under
convergence as under backup — and gains the columns a ``ConvergeRun`` needs
that a ``BackupRun`` did not: when the round started, which kind of join it
was, and the rest of the round's report as one JSON document.

The stored last-run values are cleared rather than translated. They describe a
*backup* run, and two of its statuses (``export_failed``) have no counterpart
among a round's; rendering one as though a round had produced it would put a
sentence on the status page that was never true. Nothing is lost: the next
round records a real one, and the remote's git history is the actual record of
what changed.

Revision ID: 0073
Revises: 0072
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0073"
down_revision: str | None = "0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The last-run columns the backup design left behind, blanked on the way in
#: and on the way out for the same reason: neither direction can honestly
#: restate the other's run.
_LAST_RUN_COLUMNS = ("last_run_at", "last_status", "last_error", "last_commit")


def _clear_last_run() -> None:
    assignments = ", ".join(f"{column} = NULL" for column in _LAST_RUN_COLUMNS)
    op.get_bind().execute(sa.text(f"UPDATE sync_remotes SET {assignments}"))


def upgrade() -> None:
    op.create_table(
        "sync_convergence_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pointer", sa.String(), nullable=True),
        sa.Column("pending_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_convergence_state_single_row"),
    )
    op.create_table(
        "sync_held_paths",
        sa.Column("path", sa.String(), primary_key=True),
        sa.Column("applicable", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("held_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    with op.batch_alter_table("sync_remotes") as batch:
        batch.add_column(sa.Column("last_started_at", sa.TIMESTAMP(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_join", sa.String(), nullable=True))
        batch.add_column(sa.Column("last_run_json", sa.Text(), nullable=True))
    _clear_last_run()


def downgrade() -> None:
    """Drop the convergence state and the round-shaped columns.

    The pointer is not preserved anywhere on the way down, and it should not
    be: a build below this revision does not converge, so a pointer it left
    behind would name a commit nothing had absorbed by the time convergence
    came back. Losing it makes the next round a join, which re-derives the
    base from the registry — the case that is designed for.
    """
    with op.batch_alter_table("sync_remotes") as batch:
        batch.drop_column("last_run_json")
        batch.drop_column("last_join")
        batch.drop_column("last_started_at")
    _clear_last_run()
    op.drop_table("sync_held_paths")
    op.drop_table("sync_convergence_state")
