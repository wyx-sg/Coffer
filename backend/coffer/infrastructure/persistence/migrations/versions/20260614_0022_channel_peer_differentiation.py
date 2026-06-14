"""channel_peers: sender identity + sticky preferences (ADR-023)

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-14

Adds the paired sender's identity (for the sender-aware owner gate) and the
peer's sticky structural choices (preferred agent + workspace). All nullable so
rows paired before this change degrade gracefully: a null sender_id means the
chat-id-only gate, null preferences mean the channel defaults.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("sender_id", "preferred_agent", "preferred_workspace")


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    # Idempotent ADD COLUMN (mirrors 0018): the roundtrip suite re-runs the tail
    # of the chain after a stamp-back, so adding an existing column must not error.
    for column in _COLUMNS:
        if not _has_column("channel_peers", column):
            op.execute(f"ALTER TABLE channel_peers ADD COLUMN {column} VARCHAR")


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column("channel_peers", column)
