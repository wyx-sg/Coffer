"""drop reasoning effort from the channel thread rows and stored conversations

Reasoning effort is no longer a Coffer setting. This revision drops the sticky
``channel_thread_conversations.preferred_effort`` column and removes the
``effort`` key from each conversation's stored ``agent_config`` JSON.
``workflow_node_attempts.effort`` is left as it is.

``downgrade()`` re-adds the (nullable) column; the removed values are not
recoverable.

Revision ID: 0147
Revises: 0146
Create Date: 2026-10-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0147"
down_revision: str | None = "0146"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("channel_thread_conversations") as batch:
        batch.drop_column("preferred_effort")
    op.execute(
        "UPDATE conversations SET agent_config = json_remove(agent_config, '$.effort') "
        "WHERE agent_config IS NOT NULL AND json_valid(agent_config)"
    )


def downgrade() -> None:
    with op.batch_alter_table("channel_thread_conversations") as batch:
        batch.add_column(sa.Column("preferred_effort", sa.String(), nullable=True))
