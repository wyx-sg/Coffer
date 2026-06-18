"""drop memory_projection_bindings (native projection removed, supersedes ADR-013)

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-19

Native memory projection is removed: Coffer keeps its own memory format and
agents read/write memory only through the MCP tools, so the binding table that
recorded which agent a store was projected into is no longer used. The canonical
facts in the unified ``documents`` schema are untouched, and the
``memory_store_project_roots`` table (the human-readable project identity) is
kept — only the projection bindings go.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "memory_projection_bindings"
_INDEX = "idx_projection_bindings_agent"


def _has_table(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # Idempotent: the roundtrip suite stamps back and replays the tail of the
    # chain, so dropping an already-absent table must not error.
    if _has_table(_TABLE):
        op.drop_index(_INDEX, table_name=_TABLE)
        op.drop_table(_TABLE)


def downgrade() -> None:
    # Recreate the table exactly as migration 0008 did, for a clean down-grade.
    op.create_table(
        _TABLE,
        sa.Column("store_name", sa.String(), nullable=False),
        sa.Column("agent_ref", sa.String(), nullable=False),
        sa.Column("projection_mode", sa.String(), nullable=False),
        sa.Column("target_path", sa.String(), nullable=False),
        sa.Column("native_memory_disabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("store_name", "agent_ref", name="pk_memory_projection_bindings"),
    )
    op.create_index(_INDEX, _TABLE, ["agent_ref"])
