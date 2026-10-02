"""drop ``conversations.owner``

The column existed so a workflow task's conversation stayed out of the
developer's own chat list (revision 0091). Nothing sets it any more — every
conversation is the developer's own — and the one filter that read it matched
every row. The column and its index go; the history database is the only place
the column ever lived.

The downgrade puts back the nullable column and its index, empty.

Revision ID: 0138
Revises: 0137
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0138"
down_revision: str | None = "0137"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversations"
_INDEX = "idx_conversations_owner"


def upgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column("owner")


def downgrade() -> None:
    op.add_column(_TABLE, sa.Column("owner", sa.String(), nullable=True))
    op.create_index(_INDEX, _TABLE, ["owner"])
