"""Per-tool reach overrides for custom tools.

A custom-tool group is an ``mcp_server`` of the ``http_api`` transport whose
tools are listed in its config. Each tool may narrow the group's reach to some
agents (spec mcp-gateway "Switch off or narrow one custom tool"). Reach is
machine-local (spec vault-sync "Keep reach machine-local") while the config
travels with sync, so the overrides get their own table: one row per
``(group uid, tool name)`` holding the agent uids the tool still reaches.

Nothing to back-fill: the transport is new.

Revision ID: 0115
Revises: 0114
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0115"
down_revision: str | None = "0114"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_tool_reach",
        sa.Column("resource_uid", sa.String(), primary_key=True),
        sa.Column("tool", sa.String(), primary_key=True),
        sa.Column("agents_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mcp_tool_reach")
