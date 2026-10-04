"""drop ``usage_requests.failed_over``

The model proxy sends a request to exactly one upstream, so no request is ever
moved to another provider and the column has nothing to say.

Revision ID: 0147
Revises: 0146
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0147"
down_revision: str | None = "0146"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("usage_requests") as batch:
        batch.drop_column("failed_over")


def downgrade() -> None:
    with op.batch_alter_table("usage_requests") as batch:
        batch.add_column(
            sa.Column("failed_over", sa.Boolean(), nullable=False, server_default=sa.false())
        )
