"""delete the ``secret_migrated`` audit rows

The one-time move of every secret to a minted id has run and its code is gone,
so the event type no longer exists; rows that carry it would show as unknown.

Revision ID: 0150
Revises: 0149
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0150"
down_revision: str | None = "0149"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM audit_log WHERE event_type = 'secret_migrated'")


def downgrade() -> None:
    """The deleted rows are not restored."""
