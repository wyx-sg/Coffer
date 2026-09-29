"""every resource carries a monotonic revision

The unified reconciler (ADR one-level-triggered-reconciler-compares-parameters)
is brought forward by an in-process ``Changed(kind, uid, rev)`` hint after a
write. ``updated_at`` cannot order two writes in the same clock tick, so the
row gets an integer that every write bumps. Existing rows start at 1.

Revision ID: 0107
Revises: 0106
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0107"
down_revision: str | None = "0106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column("rev", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    with op.batch_alter_table("resources") as batch_op:
        batch_op.drop_column("rev")
