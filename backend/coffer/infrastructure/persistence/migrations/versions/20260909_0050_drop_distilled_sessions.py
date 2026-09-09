"""drop the distilled_sessions ledger

Revision ID: 0050
Revises: 0049
Create Date: 2026-09-09

The database half of removing transcript distillation. ``distilled_sessions``
(0038) existed so the auto-distill catch-up sweep would never distil a settled
transcript session twice into the journal lane. Both ends of that sentence are
gone: the sweep is removed and the journal lane with it, leaving a ledger that
records work nothing performs any more.

The rows were machine-local bookkeeping, never vault data — the vault export
never carried this table — so dropping it loses no user content. What it does
end is the memory *loop*: distillation was the automatic INGEST half, and with
its DELIVER counterpart also going, memory becomes what an agent explicitly
writes with ``coffer__remember`` and reads with ``coffer__recall``. That is
simpler and more predictable, and it is a real trade: automatic accumulation
stops.

Guarded by an existence check so a database that never had the table — or one
where an earlier partial run already dropped it — still upgrades.

Irreversible in the sense that matters: ``downgrade`` recreates the empty table
so the schema round-trips, but the ledger's contents are not recoverable, and
would be meaningless without the code that wrote them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("distilled_sessions"):
        op.drop_table("distilled_sessions")


def downgrade() -> None:
    """Recreate the table's shape (empty) so the chain round-trips."""
    if _has_table("distilled_sessions"):
        return
    op.create_table(
        "distilled_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("content_sha256", sa.String(), nullable=False),
        sa.Column("distilled_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "agent_name",
            "session_id",
            "content_sha256",
            name="uq_distilled_sessions_agent_session_sha",
        ),
    )
