"""mcp_server_health table

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_server_health",
        sa.Column("resource_name", sa.String(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mcp_server_health")
