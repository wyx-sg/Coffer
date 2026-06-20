"""drop documents.locked (per-document lock removed, simplification 5.7)

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-20

The per-document co-management lock (ADR-028 pillar 3) is removed: KB
documents are always writable by humans and agents, with the F01 audit
trail plus vault backup as the safety net instead of an opt-out lock.
This drops the additive ``locked`` column added in 0025. The column lived
on the unified ``documents`` table (shared with the memory kind); memory
rows only ever carried the ``false`` default, so the drop is a no-op for
them.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    # Guarded (idempotent) DROP COLUMN, matching the 0025 convention — the
    # roundtrip suite stamps back and replays the tail of the chain.
    if _has_column("documents", "locked"):
        op.drop_column("documents", "locked")


def downgrade() -> None:
    if not _has_column("documents", "locked"):
        op.execute("ALTER TABLE documents ADD COLUMN locked BOOLEAN NOT NULL DEFAULT 0")
