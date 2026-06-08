"""memory store project roots (spec 007-memory)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-09

Records the absolute project root a per-project memory store was provisioned
from. The store ULID is a one-way hash of the git-root, so the path cannot be
recovered from the name; this mapping lets the REST surface echo the
human-readable project root back to the UI (finding #10). The global store has
no row (its project root is ``None``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_store_project_roots",
        sa.Column("store_name", sa.String(), nullable=False),
        sa.Column("project_root", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("store_name", name="pk_memory_store_project_roots"),
    )


def downgrade() -> None:
    op.drop_table("memory_store_project_roots")
