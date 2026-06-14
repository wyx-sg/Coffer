"""add conversation origin + channel-peer columns (ADR-021)

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-14

Repositioning the chat surface as the Vault Console (ADR-021) needs each
conversation to record where it was opened from: ``origin`` is ``"web"`` for a
Vault Console draft, ``"channel"`` for one an IM peer drives. For a channel
thread the peer's identity (``channel_name`` + ``peer_chat_id`` +
``peer_display_name``) is carried so the console can badge and observe it.

Existing rows predate channels-as-origin, so they default to ``"web"`` with NULL
peer fields — exactly what an un-paired conversation should report.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    # Guarded (idempotent) ADD COLUMN, matching the 0018 convention.
    if not _has_column("conversations", "origin"):
        op.execute("ALTER TABLE conversations ADD COLUMN origin VARCHAR NOT NULL DEFAULT 'web'")
    if not _has_column("conversations", "channel_name"):
        op.execute("ALTER TABLE conversations ADD COLUMN channel_name VARCHAR")
    if not _has_column("conversations", "peer_chat_id"):
        op.execute("ALTER TABLE conversations ADD COLUMN peer_chat_id VARCHAR")
    if not _has_column("conversations", "peer_display_name"):
        op.execute("ALTER TABLE conversations ADD COLUMN peer_display_name VARCHAR")


def downgrade() -> None:
    op.drop_column("conversations", "peer_display_name")
    op.drop_column("conversations", "peer_chat_id")
    op.drop_column("conversations", "channel_name")
    op.drop_column("conversations", "origin")
