"""every resource may carry a display title

Two kinds stop letting their name change — an MCP server's name prefixes every
tool name an agent sees, and a skill's is the folder an agent loads it from
(ADR names-visible-to-agents-are-fixed) — so the cosmetic reason to rename one
needs somewhere else to go. It goes here: a free-text ``title`` of at most 80
characters that surfaces show in place of the name when it is set (spec
resource-framework "Carry an optional editable title on every resource"). Every
kind gets it, fixed name or not.

Nullable with no backfill: a resource registered before this had no title, and
``NULL`` says that rather than copying the name into it. Older code ignores the
column.

Revision ID: 0104
Revises: 0103
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0105"
down_revision: str | None = "0104"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("title", sa.String(length=80), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("resources") as batch_op:
        batch_op.drop_column("title")
