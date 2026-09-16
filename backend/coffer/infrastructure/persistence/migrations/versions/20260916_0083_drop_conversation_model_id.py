"""drop conversations.model_id — nothing ever wrote it, nothing ever read it

``conversations.model_id`` arrived with the chat tables in 0012 as a
per-conversation model override, for a chat page that picked a model per
thread. That surface never shipped in that form. What replaced it is the
conversation's ``agent_config``, which carries the managed agent's own model
(ADR provider-switching) and is what the turn path actually reads; the column
beside it was written only by a PATCH branch the frontend never sent, and read
only to echo the value straight back out again.

So no vault has a non-NULL value here that means anything: creation always
passed ``None``, and the one writer was reachable only by hand-crafting a
request. Dropping it takes the whole chain with it — the domain field, the
port method, the repository update, the response and request schemas, and the
route branch.

``chat_messages.model_id`` is a different column and stays: the turn runner
records which model actually produced each assistant message, and the message
list surfaces it.

Guarded both ways, because the roundtrip suite stamps back and replays the
tail of the chain.

Revision ID: 0083
Revises: 0082
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0083"
down_revision: str | None = "0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "conversations"
_COLUMN = "model_id"


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if _has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)


def downgrade() -> None:
    """Restore the column's shape, empty.

    It was nullable with no default and no reader, so an all-NULL column is
    exactly what the chain below expects to find.
    """
    if not _has_column(_TABLE, _COLUMN):
        op.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {_COLUMN} VARCHAR")
