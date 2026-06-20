"""drop conversation origin + peer_display_name (ADR-031)

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-20

The chat surface is repositioned as the single-owner live mirror (ADR-031): the
web/channel ``origin`` dichotomy collapses to an optional channel binding
(``channel_name`` + ``peer_chat_id`` — the return address for relaying output
back to an IM channel). Under the single-owner premise the IM peer is always the
owner, so ``origin`` and ``peer_display_name`` carry no information and are
removed; "is this a channel conversation" is derived from ``channel_name`` being
set.

Guarded so the roundtrip suite (which stamps back and replays the chain tail) can
re-drop / re-add idempotently.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    if _has_column("conversations", "origin"):
        op.drop_column("conversations", "origin")
    if _has_column("conversations", "peer_display_name"):
        op.drop_column("conversations", "peer_display_name")


def downgrade() -> None:
    if not _has_column("conversations", "peer_display_name"):
        op.execute("ALTER TABLE conversations ADD COLUMN peer_display_name VARCHAR")
    if not _has_column("conversations", "origin"):
        op.execute("ALTER TABLE conversations ADD COLUMN origin VARCHAR NOT NULL DEFAULT 'web'")
