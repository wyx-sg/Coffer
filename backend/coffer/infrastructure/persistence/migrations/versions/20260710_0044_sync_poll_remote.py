"""auto-sync remote-head probe cadence (spec 010 amendment, ADR-043)

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-10

Near-real-time auto-sync probes the remote head with ``git ls-remote`` every
``poll_remote_seconds`` and runs a full sync only when the head moved; the
fixed interval becomes the fallback sweep.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> list[str]:
    return [
        row[1] for row in op.get_bind().exec_driver_sql("PRAGMA table_info(sync_config)").fetchall()
    ]


def upgrade() -> None:
    # SQLite has no IF NOT EXISTS for columns; probe first so re-running heals.
    if "poll_remote_seconds" not in _columns():
        op.execute(
            "ALTER TABLE sync_config ADD COLUMN poll_remote_seconds INTEGER NOT NULL DEFAULT 15"
        )


def downgrade() -> None:
    if "poll_remote_seconds" in _columns():
        op.execute("ALTER TABLE sync_config DROP COLUMN poll_remote_seconds")
