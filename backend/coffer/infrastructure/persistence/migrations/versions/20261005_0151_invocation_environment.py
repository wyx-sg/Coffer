"""add ``mcp_invocations.environment``

A custom-tool group's call names the environment it was made in (spec
mcp-gateway "Record invocations without content"; design
align-cli-with-ui-and-add-tool-environments D10). Nullable: every other call,
and every row written before, has none.

Revision ID: 0151
Revises: 0150
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0151"
down_revision: str | None = "0150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mcp_invocations") as batch:
        batch.add_column(sa.Column("environment", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mcp_invocations") as batch:
        batch.drop_column("environment")
