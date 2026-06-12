"""memory kind reuses the unified substrate (spec 007-memory)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-09

Redesign: the memory face shares the unified ``documents`` / ``chunks`` /
``documents_fts`` schema created by ``0006`` (discriminated by ``kind='memory'``),
so there is no memory-specific table to create. This revision is intentionally a
no-op that keeps the migration chain contiguous (``0006 -> 0007 -> head``).

The legacy ``memory_records`` table is dropped defensively in ``0006``.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No-op: memory reuses the unified documents/chunks/documents_fts tables.
    pass


def downgrade() -> None:
    pass
