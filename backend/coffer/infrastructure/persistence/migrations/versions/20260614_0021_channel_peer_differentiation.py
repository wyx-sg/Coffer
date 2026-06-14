"""channel_peers: sender identity + sticky preferences (ADR-021)

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-14

Adds the paired sender's identity (for the sender-aware owner gate) and the
peer's sticky structural choices (preferred agent + workspace). All nullable so
rows paired before this change degrade gracefully: a null sender_id means the
chat-id-only gate, null preferences mean the channel defaults.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("channel_peers", sa.Column("sender_id", sa.String(), nullable=True))
    op.add_column("channel_peers", sa.Column("preferred_agent", sa.String(), nullable=True))
    op.add_column("channel_peers", sa.Column("preferred_workspace", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("channel_peers", "preferred_workspace")
    op.drop_column("channel_peers", "preferred_agent")
    op.drop_column("channel_peers", "sender_id")
