"""drop channel_peers.preferred_workspace (workspace switching removed, 5.7→8.4)

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-20

The channel `/cwd` command and the per-binding workspace allowlist are removed
(simplification 8.4): channels collapse to the single Coffer-managed default
workspace (``~/.coffer/workspace``), so a peer no longer carries a sticky
``preferred_workspace``. This drops that column (added in 0022); the sibling
``sender_id`` and ``preferred_agent`` columns stay.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    # Guarded (idempotent) DROP COLUMN, matching the 0027 convention — the
    # roundtrip suite stamps back and replays the tail of the chain.
    if _has_column("channel_peers", "preferred_workspace"):
        op.drop_column("channel_peers", "preferred_workspace")


def downgrade() -> None:
    if not _has_column("channel_peers", "preferred_workspace"):
        op.execute("ALTER TABLE channel_peers ADD COLUMN preferred_workspace VARCHAR")
