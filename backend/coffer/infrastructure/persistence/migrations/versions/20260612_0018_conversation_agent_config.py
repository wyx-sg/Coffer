"""conversations.agent_config (spec 008 — multi-provider agent state)

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-12

A generic per-conversation JSON blob owned by the conversation's agent
provider. The built-in agent stores nothing here (its only state is the
``model_id`` column); CLI-agent providers (Claude Code, Codex) keep their
working directory and the upstream CLI session id (for ``--resume``) in it.
Nullable; ``NULL`` means "no agent-specific config". Idempotent ADD COLUMN.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    if not _has_column("conversations", "agent_config"):
        op.execute("ALTER TABLE conversations ADD COLUMN agent_config TEXT")


def downgrade() -> None:
    op.drop_column("conversations", "agent_config")
