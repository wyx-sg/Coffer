"""add ``mcp_invocations.content_json``

A call's redacted, bounded content — its arguments, result, error and a custom
tool's request and response (spec mcp-gateway "Record invocations with
redacted, bounded content"). Nullable: a row written before, or while
recording was off, has none.

Revision ID: 0152
Revises: 0151
Create Date: 2026-10-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0152"
down_revision: str | None = "0151"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mcp_invocations") as batch:
        batch.add_column(sa.Column("content_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mcp_invocations") as batch:
        batch.drop_column("content_json")
