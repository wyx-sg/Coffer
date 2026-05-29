"""mcp tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_capability_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("capability_type", sa.String(), nullable=False),
        sa.Column("capability_key", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "resource_id",
            "capability_type",
            "capability_key",
            name="uq_mcp_prefs_resource_type_key",
        ),
    )
    op.create_index(
        "idx_prefs_resource",
        "mcp_capability_preferences",
        ["resource_id", "capability_type", "enabled"],
    )

    op.create_table(
        "mcp_invocations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("resource_name", sa.String(), nullable=False),
        sa.Column("capability_type", sa.String(), nullable=False),
        sa.Column("capability_key", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
    )
    op.create_index(
        "idx_invocations_resource",
        "mcp_invocations",
        ["resource_name", "timestamp"],
    )
    op.create_index("idx_invocations_time", "mcp_invocations", ["timestamp"])
    op.create_index(
        "idx_invocations_session",
        "mcp_invocations",
        ["session_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("idx_invocations_session", table_name="mcp_invocations")
    op.drop_index("idx_invocations_time", table_name="mcp_invocations")
    op.drop_index("idx_invocations_resource", table_name="mcp_invocations")
    op.drop_table("mcp_invocations")
    op.drop_index("idx_prefs_resource", table_name="mcp_capability_preferences")
    op.drop_table("mcp_capability_preferences")
