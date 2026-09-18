"""A conversation says whose it is.

Every conversation in this vault was the developer's own until a workflow task
became one (spec workflow, FR-019/FR-030). A task's conversation is created
through the same service and stored in the same table — which is the point, and
what makes its transcript ordinary — but it belongs to the RUN, and the chat
list was showing all of them: three rows reading "# Workflow node: Draft the
TD" in a list of the developer's own threads.

``owner`` is NULL for a conversation the developer started and names the
surface that owns it otherwise. The chat list shows only the NULL ones, so the
chat layer needs to know nothing about workflows — only that a conversation
with an owner is not its own. Reading one by id is untouched: the task's page
opens its conversation, and a link to it must keep working.

Nothing needs backfilling. Every row that exists when this runs was created by
chat itself, which is exactly what NULL means; a workflow conversation created
before this column existed would be indistinguishable from a chat one, and
there is no vault holding one — the `workflow` kind ships in the same release
as this column.

Revision ID: 0091
Revises: 0090
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

_TABLE = "conversations"
_INDEX = "idx_conversations_owner"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("owner", sa.String(), nullable=True))
    # The chat list filters on it on every read of the page.
    op.create_index(_INDEX, _TABLE, ["owner"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "owner")
