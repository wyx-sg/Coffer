"""drop the subscription quota snapshots

Usage now shows only what Coffer's proxy metered; the official quota each
subscription agent reported (``quota_snapshots``, created by 0111) is no longer
read, stored or shown, so its table goes. The usage tables stay.

The downgrade recreates the table empty; the readings were a cache of what the
agents' own feeds last said and refill themselves.

Revision ID: 0140
Revises: 0139
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0140"
down_revision: str | None = "0139"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "quota_snapshots" in inspector.get_table_names():
        op.drop_table("quota_snapshots")


def downgrade() -> None:
    op.create_table(
        "quota_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_type", sa.String(), nullable=False),
        sa.Column("window_key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("used_percent", sa.Float(), nullable=False),
        sa.Column("window_minutes", sa.Integer(), nullable=True),
        sa.Column("resets_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("plan", sa.String(), nullable=True),
        sa.UniqueConstraint("agent_type", "window_key", name="uq_quota_snapshots_window"),
    )
