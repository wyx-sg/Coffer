"""agent kind tables (spec 004-agent-registry)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-25

Adds the `suppressed_agent_types` table that records agent types whose
auto-detection has been suppressed because the user manually removed an
auto-detected agent. The skill_agent_bindings join table will land later
under spec 005-skill-manager (joint delivery).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suppressed_agent_types",
        # Bound the column length so a stray caller can't insert kilobyte
        # blobs. 64 mirrors the AgentCreate.name pattern and is generous for
        # any plausible agent_type enum value.
        sa.Column("agent_type", sa.String(length=64), primary_key=True),
        sa.Column("suppressed_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("suppressed_agent_types")
