"""the one backup remote exports are pushed to

Revision ID: 0062
Revises: 0061
Create Date: 2026-09-12

Spec vault-export-import ``## Backup``, constitution 0.5.0. The table holds a
single row: ``id`` is pinned to 1 by a check constraint, so "at most one backup
remote" cannot drift into "however many rows got inserted" the first time some
caller forgets to look before inserting.

``credential_ref`` names a secret in the credential store; the secret itself is
never written here, so this table can be read into an API response or a log
line without redaction.

Creates the table empty. Backup is off until the user points Coffer at a
repository they own, so there is no row to backfill and nothing to infer about
existing installations.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_remotes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("branch", sa.String(), nullable=False, server_default="main"),
        sa.Column("credential_ref", sa.String(), nullable=True),
        sa.Column("include_credentials", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("worktree_path", sa.String(), nullable=False, server_default="~/.coffer/sync"),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("last_commit", sa.String(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_sync_remote_single_row"),
        sa.CheckConstraint("interval_seconds > 0", name="ck_sync_remote_interval_positive"),
    )


def downgrade() -> None:
    """Drop the table — configuring a remote again is the way back.

    The row holds a URL and a credential reference the user typed, not data
    Coffer produced; the backups themselves live on the remote and survive this.
    """
    op.drop_table("sync_remotes")
