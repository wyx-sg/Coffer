"""add documents.deleted_at (recoverable soft-delete / trash, ADR-030)

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-19

KB documents gain a recoverable soft-delete (ADR-030): deleting a live document
moves it to a trash (its ``docs/<id>.md`` + index rows are removed, but the
original ``raw/`` and the row are kept with ``deleted_at`` set), and it can be
restored. The nullable ``deleted_at`` column is additive on the unified
``documents`` table (shared with the memory kind); memory never sets it (its
``forget`` is a hard delete), so memory rows keep ``NULL`` and live reads — which
filter ``deleted_at IS NULL`` — are unaffected for the memory face.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    # Guarded (idempotent) ADD COLUMN, matching the 0025 convention. Nullable
    # with no default — NULL means "live"; a timestamp means "in trash".
    if not _has_column("documents", "deleted_at"):
        op.execute("ALTER TABLE documents ADD COLUMN deleted_at TIMESTAMP")


def downgrade() -> None:
    if _has_column("documents", "deleted_at"):
        op.drop_column("documents", "deleted_at")
