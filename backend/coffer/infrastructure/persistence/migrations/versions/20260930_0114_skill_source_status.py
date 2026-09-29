"""A Git-imported skill's update checks, kept on this machine.

One table for spec skill-manager "Update a Git-imported skill from its
source": when this machine last checked a skill's repository, the last check
that reached it, git's message when one did not, what the ref points at now,
how many commits and files that is past the pin, and a commit the user chose
to keep their edits against. The pin itself stays in the skill's config (the
``git_import`` source); this is observation, never synced, and goes with its
skill.

Nothing to back-fill: no skill had a Git source before this revision.

Revision ID: 0114
Revises: 0113
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0114"
down_revision: str | None = "0113"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skill_source_status",
        sa.Column(
            "skill_resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latest_commit", sa.String(), nullable=True),
        sa.Column("commits_ahead", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dismissed_commit", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("skill_source_status")
