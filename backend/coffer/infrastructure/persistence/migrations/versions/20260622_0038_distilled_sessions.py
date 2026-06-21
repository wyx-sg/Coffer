"""distilled_sessions: auto-distill catch-up sweep idempotency ledger (007 FR-046)

Revision ID: 0038
Revises: 0037
Create Date: 2026-06-22

Adds the machine-local ``distilled_sessions`` ledger that the auto-distill
catch-up sweep consults so a settled transcript session is never double-distilled
into the journal lane. One row per ``(agent_name, session_id, content_sha256)``;
a material content change yields a new sha and is therefore eligible to
re-distill. This ledger is the idempotency key the future SessionEnd hook
(slice 6) will share.

Idempotent on a DB that already has the table (the roundtrip suite stamps back
and replays the chain tail). Reversible (drops the table).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
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


def downgrade() -> None:
    if _has_table("distilled_sessions"):
        op.drop_table("distilled_sessions")
