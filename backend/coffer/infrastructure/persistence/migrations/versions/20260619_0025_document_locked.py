"""add documents.locked (per-document co-management lock, ADR-028)

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-19

KB documents become co-managed by humans and agents (ADR-028). A per-document
``locked`` flag lets an authoritative document opt out of all mutation: while
locked, edit / reconvert / re-upload-replace / delete are refused for every
caller. The column is additive on the unified ``documents`` table (shared with
the memory kind); memory rows simply carry the ``false`` default and ignore it.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    # Guarded (idempotent) ADD COLUMN, matching the 0021 convention — the
    # roundtrip suite stamps back and replays the tail of the chain.
    if not _has_column("documents", "locked"):
        op.execute("ALTER TABLE documents ADD COLUMN locked BOOLEAN NOT NULL DEFAULT 0")


def downgrade() -> None:
    if _has_column("documents", "locked"):
        op.drop_column("documents", "locked")
