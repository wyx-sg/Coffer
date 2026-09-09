"""narrow agent types to claude_code and codex

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-09

Agents live in the generic ``resources`` table as ``kind='agent'`` rows whose
``config_json`` carries ``"type": "<agent_type>"``. Once the enum loses the four
removed members (``cursor`` / ``opencode`` / ``openclaw`` / ``hermes``),
``AgentConfig.model_validate`` raises on any stored row still carrying one,
which would 500 every agent listing. A removed-type agent is non-functional
anyway, so dropping the row is the only coherent outcome.

Revision 0031 cut the same four types once before, back when they had never
shipped; they were re-introduced afterwards and really were delivered, so this
time a real install can genuinely hold such rows.

Files Coffer wrote into those agents' config directories (its own MCP entry,
hooks, skill symlinks) are deliberately left alone: this migration owns the
database, not the user's other tools. The daemon names the leftover paths once
at startup so the user can decide whether to clean them up.

Idempotent: a second run finds no matching rows and is a no-op. Migration
scripts never import application code, so the removed values are inlined here
and stay frozen as the model evolves.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM resources "
            "WHERE kind = 'agent' "
            "AND json_extract(config_json, '$.type') IN "
            "('cursor', 'opencode', 'openclaw', 'hermes')"
        )
    )


def downgrade() -> None:
    # Lossy by nature: the deleted rows carried no recoverable state beyond a
    # config dir the user can re-register in one action, and a removed type
    # cannot be reconstructed. The schema itself is unchanged, so there is
    # nothing structural to restore.
    pass
