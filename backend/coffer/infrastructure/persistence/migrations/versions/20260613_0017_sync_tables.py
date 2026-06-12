"""sync_config and sync_state tables for multi-machine sync (spec 010)

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-13

Two singleton rows (id = 1): sync_config holds the user's remote/branch and the
enabled/auto toggles; sync_state holds the last-run status, conflict paths, and
locked credential refs. No secrets — git auth is the user's ambient git config.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("remote", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("branch", sa.String(), nullable=False, server_default="main"),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False, server_default="unconfigured"),
        sa.Column("last_sync_at", sa.String(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("conflict_paths_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("locked_refs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sync_state")
    op.drop_table("sync_config")
