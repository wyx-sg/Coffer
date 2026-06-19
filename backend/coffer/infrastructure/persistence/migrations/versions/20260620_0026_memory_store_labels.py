"""add memory_store_labels (user-set display label for a memory store, 007 FR-017c)

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-20

A per-project memory store is named ``project-<ULID>``; when its originating
git-root was never recorded the UI shows that opaque name. This table lets the
user attach a readable display label to any store (``store_name -> label``),
mirroring ``memory_store_project_roots``. Additive — no existing row changes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    # Guarded create (idempotent) — the roundtrip suite stamps back and replays
    # the tail of the chain.
    if not _has_table("memory_store_labels"):
        op.create_table(
            "memory_store_labels",
            sa.Column("store_name", sa.String(), primary_key=True),
            sa.Column("label", sa.String(), nullable=False),
        )


def downgrade() -> None:
    if _has_table("memory_store_labels"):
        op.drop_table("memory_store_labels")
