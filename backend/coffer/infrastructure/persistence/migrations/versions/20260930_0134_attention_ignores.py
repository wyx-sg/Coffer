"""attention items a person ignored on this machine

The Overview lets a person ignore an informational "needs you" item — an agent
left unconnected on purpose — so it leaves the list, the sidebar's badges and
the menu bar's count alike (spec web-ui "Let the user ignore an unconnected
agent on Overview"). One row per ignored item key. The downgrade drops the
table: an older build has no notion of ignoring and lists every item again.

Revision ID: 0134
Revises: 0133
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0134"
down_revision: str | None = "0133"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attention_ignores",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("ignored_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("attention_ignores")
