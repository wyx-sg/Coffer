"""global knowledge-base chunking defaults (spec 006)

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-12

Chunking is configured globally (a default, overridable per knowledge base):
add ``default_chunk_size`` / ``default_chunk_overlap`` to the global config
singleton. Idempotent (``ADD COLUMN`` guarded) so a partially-migrated DB heals.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def _add_column(name: str, default: int) -> None:
    if not _has_column("embedding_config", name):
        op.execute(
            f"ALTER TABLE embedding_config ADD COLUMN {name} INTEGER NOT NULL DEFAULT {default}"
        )


def upgrade() -> None:
    _add_column("default_chunk_size", 512)
    _add_column("default_chunk_overlap", 64)


def downgrade() -> None:
    # SQLite can't drop columns cleanly pre-3.35; the columns are harmless and
    # the singleton is small, so downgrade leaves them.
    pass
