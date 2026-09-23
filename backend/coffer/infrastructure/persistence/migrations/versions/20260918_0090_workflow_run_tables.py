"""the four tables a workflow run executes in

A workflow *template* gets no table: it is one row in ``resources`` with
``kind = 'workflow'``, so it takes the framework's lifecycle, audit, schema
validation and sync for free (spec workflow). What has no home in that row is the
*execution* — a run is operational state, not a curated asset, it is owned by
one machine, and it must not travel with the vault the way a template does.

So four tables arrive together, because they only make sense together:

``workflow_runs`` is one run. Its ``template_snapshot`` is the definition
frozen at creation — the run executes the snapshot, never the template as it
stands today, so editing a template cannot change a run already under way.
``status``, ``current_stage_key``, ``current_node_key`` and ``tokens_spent``
are projections of the event log, stored so listing runs is one row read rather
than a fold, and rebuilt from the events on daemon start. ``version`` is the
optimistic lock every mutating command carries. ``template_ref`` is
deliberately *not* a foreign key: deleting a template is permitted and leaves
the reference dangling by design, the way a deleted source leaves an artifact's
provenance intact.

``workflow_events`` is the record of truth: append-only, with ``sequence``
monotonic inside a run and unique with it, so a duplicate or a re-ordering is
a constraint violation rather than a quietly rewritten history.

``workflow_node_attempts`` is one attempt at one node. A retry inserts
``attempt + 1`` rather than rewriting the row, which is what keeps the earlier
attempt's conversation readable after it.

``workflow_approvals`` is a held decision carrying the exact payload that will
execute. Its terminal states make a repeated decision idempotent.

The three child tables cascade from ``workflow_runs`` in the schema rather
than in application code: the engine runs with ``PRAGMA foreign_keys = ON``,
so deleting a run cannot leave orphaned events behind even if a future caller
forgets. Node *conversations* are not cascaded — they are ordinary
conversations and belong to the chat layer's own retention.

Idempotent in both directions: each table is created only when absent and
dropped only when present, because this runs at daemon startup and the
roundtrip suite stamps back and replays the tail of the chain.

Revision ID: 0090
Revises: 0089
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0090"
down_revision: str | None = "0089"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Drop order: children first, parent last. SQLite enforces the foreign keys
#: (``PRAGMA foreign_keys = ON``), so dropping ``workflow_runs`` while a row in
#: any of the other three still points at it fails the constraint.
_DROP_ORDER = (
    "workflow_approvals",
    "workflow_node_attempts",
    "workflow_events",
    "workflow_runs",
)


def _has_table(name: str) -> bool:
    return name in set(inspect(op.get_bind()).get_table_names())


def _create_runs() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("template_ref", sa.String(), nullable=True),
        sa.Column("template_snapshot", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("workdir", sa.String(), nullable=False),
        sa.Column("machine_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_stage_key", sa.String(), nullable=True),
        sa.Column("current_node_key", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tokens_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inputs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    # One index per question the list surface asks: "which runs are active"
    # and "what changed most recently".
    op.create_index("idx_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("idx_workflow_runs_updated", "workflow_runs", ["updated_at"])


def _create_events() -> None:
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor", sa.JSON(), nullable=False),
        sa.Column("stage_key", sa.String(), nullable=True),
        sa.Column("node_key", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sequence", name="uq_workflow_events_run_sequence"),
    )
    op.create_index("idx_workflow_events_run", "workflow_events", ["run_id", "sequence"])


def _create_attempts() -> None:
    op.create_table(
        "workflow_node_attempts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_key", sa.String(), nullable=False),
        sa.Column("node_key", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "run_id", "node_key", "attempt", name="uq_workflow_attempts_run_node_attempt"
        ),
    )
    op.create_index("idx_workflow_attempts_run", "workflow_node_attempts", ["run_id"])


def _create_approvals() -> None:
    op.create_table(
        "workflow_approvals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attempt_id",
            sa.String(),
            sa.ForeignKey("workflow_node_attempts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_surface", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # A run's pending approvals are the only ones anything asks for, so the
    # index answers "(this run, still pending)" rather than run alone.
    op.create_index("idx_workflow_approvals_run", "workflow_approvals", ["run_id", "status"])


def upgrade() -> None:
    if not _has_table("workflow_runs"):
        _create_runs()
    if not _has_table("workflow_events"):
        _create_events()
    if not _has_table("workflow_node_attempts"):
        _create_attempts()
    if not _has_table("workflow_approvals"):
        _create_approvals()


def downgrade() -> None:
    """Drop all four.

    Nothing is preserved on the way down and nothing should be: a build below
    this revision has no engine to advance a run and no surface that reads
    one. The templates survive untouched — they are ``resources`` rows, which
    this migration never touched.
    """
    for table in _DROP_ORDER:
        if _has_table(table):
            op.drop_table(table)
