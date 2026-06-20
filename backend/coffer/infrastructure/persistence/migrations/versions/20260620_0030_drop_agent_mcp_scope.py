"""drop agent mcp scope tables (per-agent scoping removed, simplification 1.6)

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-20

Per-agent MCP server scoping (auto/selected) is removed (simplification 1.6,
reverts PR #108 / ADR-026-per-agent-mcp-scoping): the gateway serves every
enabled server to every agent again, with no per-agent identity or allowlist.
This drops the two tables added in 0023 (``agent_mcp_scope`` +
``agent_mcp_scope_server``). Guarded/idempotent — a re-run over a DB that
already lacks them is a no-op. ``downgrade`` recreates them (mirroring 0023's
upgrade) so the chain stays reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # SQLite drops a table's indexes with the table, so dropping the table is
    # enough (no explicit drop_index needed).
    if _has_table("agent_mcp_scope_server"):
        op.drop_table("agent_mcp_scope_server")
    if _has_table("agent_mcp_scope"):
        op.drop_table("agent_mcp_scope")


def downgrade() -> None:
    # Recreate the tables exactly as 0023 did (idempotent guard mirrors 0023).
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
