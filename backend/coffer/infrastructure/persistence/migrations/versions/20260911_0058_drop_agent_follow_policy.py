"""strip the retired follow policy out of every stored agent config

Skill delivery used to be decided by three overlapping mechanisms: the skill's
``scope``, the agent's follow policy (``follow_all_skills`` +
``skill_exclusions`` inside a ``kind='agent'`` row's ``config_json``), and the
per-(skill, agent) binding's own ``enabled`` flag. It is now decided by one, the
same rule ``mcp_server`` already used::

    delivered(skill, agent) == skill.enabled and agent_in_scope(skill.scope, agent)

The follow policy is gone from ``AgentConfig``, which declares
``extra="forbid"`` — so a row still carrying either key fails to validate, and
every read of that agent (the Agents page, skill delivery, the config-file
editor) raises. A migration is one-shot: the keys are removed from the data
here and NO load-time shim is left behind to tolerate them.

Idempotent: a second run finds no row carrying either key and matches nothing.
The key names are inlined rather than imported — a migration must mean the same
thing forever, and importing the model would make this revision's behaviour
change as the model evolves.

Irreversible by nature: which skills an agent had excluded, and whether it
followed at all, cannot be reconstructed — and the model that read them no
longer exists.

Revision ID: 0056
Revises: 0055
Create Date: 2026-09-10
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The two retired ``AgentConfig`` keys, frozen at this revision.
_RETIRED_KEYS = ("follow_all_skills", "skill_exclusions")


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'agent'")
    ).fetchall()
    for row_id, raw in rows:
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue  # a row the app cannot read either; not this script's to fix
        if not isinstance(config, dict):
            continue
        if not any(key in config for key in _RETIRED_KEYS):
            continue
        for key in _RETIRED_KEYS:
            config.pop(key, None)
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(config), "id": row_id},
        )


def downgrade() -> None:
    """No-op: the removed policy is not recoverable, and nothing reads it."""
