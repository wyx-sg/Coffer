"""drop persisted agents of removed types (simplification: 6 agent types -> 2)

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-20

Coffer now supports exactly two agent types, ``claude_code`` and ``codex``; the
``cursor`` / ``opencode`` / ``openclaw`` / ``hermes`` types are removed from the
``AgentType`` enum. Agents live in the generic ``resources`` table as
``kind='agent'`` rows whose ``config_json`` carries ``"type": "<agent_type>"``.
Once the enum loses those members, ``AgentConfig.model_validate`` raises on any
stored row still carrying a removed type, which would 500 every agent listing.

These four types shipped ``enabled=False`` (never surfaced in the add flow), so
such rows are unlikely to exist on a real install — but this data migration
defensively deletes them so an upgraded DB cannot crash on load. A removed-type
agent is non-functional anyway (its type no longer exists), so dropping the row
is the only coherent outcome.

Idempotent: a second run (or a DB stamped mid-migration) finds no matching rows
and is a no-op. Migration scripts never import application code, so the removed
type values are inlined here and stay frozen as the model evolves.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM resources "
            "WHERE kind = 'agent' "
            "AND json_extract(config_json, '$.type') IN "
            "('cursor', 'opencode', 'openclaw', 'hermes')"
        )
    )


def downgrade() -> None:
    # Lossy by nature: the deleted rows carried a type the older enum still knew,
    # but their full config is gone and cannot be reconstructed. The older schema
    # is otherwise unchanged, so there is nothing structural to restore.
    pass
