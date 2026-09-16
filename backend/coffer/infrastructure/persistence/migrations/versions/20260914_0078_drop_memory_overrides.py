"""drop the developer's memory overrides, table and audit trail together

The memory partition surface is a file tree now: the partition's own directory
on the left, a read-only preview on the right. The per-fact actions that used
to sit beside each fact — hide, pin, mark-superseded-by, settle-a-conflict —
are gone, and with no surface to record a decision there is nothing left to
store. This is a **deliberate reduction of a capability that worked**, decided
by the project owner, not the cleanup of something unused.

It costs more than the four buttons. ``memory_overrides`` was the only
non-derived state the memory layer held, and therefore the only part of it
that converged with the sync remote — the requirement saying so is retired in
this same change: everything under ``~/.coffer/memory/`` is aggregated from the
agents installed on *this* machine and deliberately stays here (spec memory
FR-016). So dropping this table removes the last memory-related thing that
travelled between the user's machines. A hide made on the laptop will no longer
be known to the desktop, because there are no hides.

The rows go with the table rather than being kept "just in case". They are
keyed by a fact key and nothing reads a fact key any more; a row no code can
name is a row every reader has to cope with and none can use — the argument
0055, 0069 and 0077 each made about audit rows, applied here to the table
itself.

Two retired audit event types are purged for that same reason.
``memory_override_set`` and ``memory_override_cleared`` go with their enum
members and their locale labels — but the rows exist in live vaults, and
``coffer__diagnose`` hands an agent a window of this table when something has
gone wrong with Coffer. An event nothing can label costs more there than the
record is worth. The names are inlined rather than imported, as 0077 was and
for the same reason: a migration must mean the same thing forever, and the
constants it named are deleted in this same change.

Idempotent: a vault that never recorded a decision matches no rows and, if it
somehow lacks the table, skips the drop. Irreversible in substance — the
downgrade recreates the table's shape so the chain stays reversible, but the
decisions themselves are not inventable back, and there is no surface left
that would write new ones.

Revision ID: 0078
Revises: 0077
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0078"
down_revision: str | None = "0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "memory_overrides"

#: The retired event types' stored values, frozen here.
_RETIRED_EVENTS = ("memory_override_set", "memory_override_cleared")


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table(_TABLE):
        op.drop_table(_TABLE)
    op.get_bind().execute(
        sa.text("DELETE FROM audit_log WHERE event_type IN (:set_event, :cleared_event)"),
        {"set_event": _RETIRED_EVENTS[0], "cleared_event": _RETIRED_EVENTS[1]},
    )


def downgrade() -> None:
    """Recreate the table's shape, empty.

    The rows cannot come back — neither the decisions nor the audit of them —
    so this restores the schema the chain below expects and nothing more. That
    is the same bargain every drop in this directory strikes: reversibility is
    a property of the migration chain, not a promise about the data.
    """
    if _has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("fact_key", sa.String(), primary_key=True),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("superseded_by", sa.String(), nullable=False, server_default=""),
        sa.Column("conflict_choice", sa.String(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(), nullable=False, server_default="system"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
