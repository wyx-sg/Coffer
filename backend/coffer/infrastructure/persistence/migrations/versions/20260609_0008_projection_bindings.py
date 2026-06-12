"""memory projection bindings (spec 007-memory)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-09

Records which agents have a native memory projection established for a given
memory store, so the projection engine can re-render on every memory change and
the agent-detail surfaces can list/remove a binding. Pure binding state — the
canonical facts live in the unified ``documents`` schema; this table only maps
``(store_name, agent_ref)`` to the projection mode + native target path.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_projection_bindings",
        sa.Column("store_name", sa.String(), nullable=False),
        sa.Column("agent_ref", sa.String(), nullable=False),
        sa.Column("projection_mode", sa.String(), nullable=False),
        sa.Column("target_path", sa.String(), nullable=False),
        sa.Column("native_memory_disabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("store_name", "agent_ref", name="pk_memory_projection_bindings"),
    )
    op.create_index(
        "idx_projection_bindings_agent",
        "memory_projection_bindings",
        ["agent_ref"],
    )


def downgrade() -> None:
    op.drop_index("idx_projection_bindings_agent", table_name="memory_projection_bindings")
    op.drop_table("memory_projection_bindings")
