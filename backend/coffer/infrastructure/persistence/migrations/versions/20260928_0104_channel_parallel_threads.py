"""A direct chat's thread says whether it is a parallel conversation.

A direct chat is one conversation (spec channels "Open parallel conversations in
a direct chat"). The owner opens further ones beside it with ``/thread``, and
each such thread is a row of ``channel_thread_conversations`` that carries:

* ``parallel_ordinal`` — its number within the chat, ``max + 1`` over the
  chat's rows, so a number is never reused after a conversation is replaced;
* ``parallel_title`` — the title the owner gave it, from which the mark
  ``🧵#N title`` is built wherever the thread is shown.

A row with no ordinal is not a parallel thread. Nothing is backfilled: the
direct-chat thread rows that exist today were casual replies-in-thread, and
leaving them without an ordinal is what folds them into the direct chat's
conversation — the intended behaviour.

Revision ID: 0104
Revises: 0103
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0104"
down_revision: str | None = "0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "channel_thread_conversations"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("parallel_ordinal", sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column("parallel_title", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "parallel_title")
    op.drop_column(_TABLE, "parallel_ordinal")
