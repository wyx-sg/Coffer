"""drop channel_peers.active_conversation_id and .preferred_agent

Both were superseded by ``channel_thread_conversations`` (0041) and then left
behind. That table keys the conversation a turn drives and the agent it opens
with by ``(resource_id, chat_id, thread_id)``, because a group's threads must
not collide on one conversation — and 0041 copied the peer's two values into
it as the DM row's starting point. Nothing has written the peer copies since:
every read in the channel layer goes to the thread row, and the two peer
writers that remained (``set_active_conversation``, ``set_preferences``) had no
caller outside the test suite.

That made them worse than unused. ``channel status`` read
``channel_peers.active_conversation_id`` and so reported "conv: -" for a
channel that had been in conversation for weeks, and the synced pairing area
published ``preferred_agent`` — always NULL — as though a machine's sticky
agent choice travelled. Both now read the thread row, which is the one that
knows.

Two columns' values are discarded rather than migrated. 0041 already moved
them forward; whatever is in these columns today is the state of the world
before that migration ran, which every reader has ignored ever since. There is
nothing here that is newer than the row it was copied to.

Idempotent in both directions, because the roundtrip suite stamps back and
replays the tail of the chain.

Revision ID: 0084
Revises: 0083
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0084"
down_revision: str | None = "0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "channel_peers"
_COLUMNS = ("active_conversation_id", "preferred_agent")


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    for column in _COLUMNS:
        if _has_column(_TABLE, column):
            op.drop_column(_TABLE, column)


def downgrade() -> None:
    """Restore both columns' shape, empty.

    Each was nullable with no default and — for the whole window this
    migration describes — no writer, so an all-NULL column is exactly what the
    chain below expects to find. The values themselves live on in
    ``channel_thread_conversations``, where 0041 put them.
    """
    for column in _COLUMNS:
        if not _has_column(_TABLE, column):
            op.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {column} VARCHAR")
