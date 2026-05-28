"""skill kind tables (spec 005-skill-manager)

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-26

Adds the skill_agent_bindings join table that the skill manager owns.
The suppressed_agent_types table came in with 0005_agent_tables
(spec 004-agent-registry); this migration chains after it as part of
the one-spec-one-PR layout.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skill_agent_bindings",
        sa.Column(
            "skill_resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_linked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_link_path", sa.Text(), nullable=True),
        sa.Column("link_mode", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint(
            "skill_resource_id",
            "agent_resource_id",
            name="pk_skill_agent_bindings",
        ),
    )
    op.create_index(
        "idx_bindings_agent",
        "skill_agent_bindings",
        ["agent_resource_id", "enabled"],
    )
    op.create_index(
        "idx_bindings_skill",
        "skill_agent_bindings",
        ["skill_resource_id", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("idx_bindings_skill", table_name="skill_agent_bindings")
    op.drop_index("idx_bindings_agent", table_name="skill_agent_bindings")
    op.drop_table("skill_agent_bindings")
