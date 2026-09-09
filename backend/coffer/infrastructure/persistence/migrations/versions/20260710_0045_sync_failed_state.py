"""failed state-doc paths in sync_state (spec 010 slice 7 amendment)

Revision ID: 0045
Revises: 0044
Create Date: 2026-07-10

A state-area doc whose import failed must be preserved verbatim by the next
export (mirroring resource quarantine) instead of being owned-replaced with
this machine's stale local value — otherwise one transient failure silently
reverts the fleet.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> list[str]:
    return [
        row[1] for row in op.get_bind().exec_driver_sql("PRAGMA table_info(sync_state)").fetchall()
    ]


def upgrade() -> None:
    if "failed_state_json" not in _columns():
        op.execute("ALTER TABLE sync_state ADD COLUMN failed_state_json TEXT NOT NULL DEFAULT '[]'")


def downgrade() -> None:
    if "failed_state_json" in _columns():
        op.execute("ALTER TABLE sync_state DROP COLUMN failed_state_json")
