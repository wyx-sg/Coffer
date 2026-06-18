"""agent mcp scope tables (ADR-026)

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-19

Adds per-agent MCP server scoping: ``agent_mcp_scope`` holds each agent's mode
(auto | selected) and ``agent_mcp_scope_server`` holds the allowlist used when
mode = 'selected'. Both cascade-delete with their agent or server resource.
Existing agents have no rows and are therefore treated as ``auto`` (every
enabled server), preserving the prior whole-gateway-per-agent behaviour.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Idempotent (matches 0019): a re-run over a DB that already has these
    # tables must be a no-op rather than failing on CREATE TABLE.
    if _has_table("agent_mcp_scope") and _has_table("agent_mcp_scope_server"):
        return
    op.create_table(
        "agent_mcp_scope",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(), nullable=False, server_default=sa.text("'auto'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_resource_id", name="uq_agent_mcp_scope_agent"),
        sa.CheckConstraint("mode IN ('auto', 'selected')", name="ck_agent_mcp_scope_mode"),
    )
    op.create_table(
        "agent_mcp_scope_server",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "server_resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "agent_resource_id", "server_resource_id", name="uq_agent_mcp_scope_server"
        ),
    )
    op.create_index(
        "idx_agent_scope_server_agent",
        "agent_mcp_scope_server",
        ["agent_resource_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_scope_server_agent", table_name="agent_mcp_scope_server")
    op.drop_table("agent_mcp_scope_server")
    op.drop_table("agent_mcp_scope")
