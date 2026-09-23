"""conversations.agent_key stops defaulting to ``builtin``

0012 created ``conversations.agent_key`` with ``server_default='builtin'``,
from when a built-in chat persona could own a conversation. That persona is
withdrawn: every conversation now belongs to a managed agent, and every writer
names it. A default left at the storage level turns a writer that forgets to
name the agent into a row routed to an agent that no longer exists, instead of
the refusal it should be (spec chat, "Require every writer to name the agent").

SQLite cannot drop a column default in place, so the table is rebuilt through
``batch_alter_table``; the rows, the ``NOT NULL`` and the indexes come across
unchanged. No table references ``conversations`` by foreign key, so the copy
and swap disturbs nothing outside it.

Revision ID: 0102
Revises: 0101
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0102"
down_revision: str | None = "0101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversations", recreate="always") as batch:
        batch.alter_column(
            "agent_key",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations", recreate="always") as batch:
        batch.alter_column(
            "agent_key",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default="builtin",
        )
