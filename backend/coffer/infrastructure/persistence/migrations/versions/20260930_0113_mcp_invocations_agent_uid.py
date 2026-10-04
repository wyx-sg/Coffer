"""mcp_invocations names the calling agent

Adds a nullable ``agent_uid`` column to ``mcp_invocations`` (spec mcp-gateway
"Record invocations without content"): the uid the session's shim reported on
``initialize``, so the log can say which agent made each call and be read for
one agent alone. Null for a session that reported no agent, and for every row
written before this revision — the log never knew, so it does not guess.

An index on ``(agent_uid, timestamp)`` mirrors the per-server and per-session
ones: the per-agent read is newest-first over one agent's rows.

Not a foreign key, like ``resource_uid``: a deleted agent's calls stay in the
history.

Revision ID: 0113
Revises: 0112
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0113"
down_revision: str | None = "0112"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "mcp_invocations"
_INDEX = "idx_invocations_agent"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("agent_uid", sa.String(), nullable=True))
    op.create_index(_INDEX, _TABLE, ["agent_uid", "timestamp"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "agent_uid")
