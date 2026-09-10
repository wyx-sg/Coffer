"""strip agent config keys the model no longer declares

Revision ID: 0056
Revises: 0055
Create Date: 2026-09-10

``AgentConfig`` is ``extra="forbid"``, so a stored ``kind='agent'`` config
still carrying a removed field fails to load — and ``GET /api/v1/agents``
answers 422, taking the Agents page down on every install that predates the
removal. Two such keys accumulated without ever being stripped at rest:

- ``disable_native_memory`` — removed with FR-046 (#323), which retired the
  hook that turned the agent's own write-side memory off.
- ``auto_detected`` — removed when detection became confirm-based (a detected
  agent registers exactly like a manual add), so the flag had nothing to say.

Until now both were tolerated by a before-validator on ``AgentConfig``. That
tolerance is deleted alongside this revision: the data is fixed once, here, and
the model stays honest about the fields it actually has.

Idempotent: stripping absent keys is a no-op, so a re-run (or a DB stamped
mid-migration) converges.

Migration scripts never import application code — the field names are inlined
here and stay frozen as the model evolves.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Keys no version of ``AgentConfig`` still declares.
_DEAD_FIELDS = ("disable_native_memory", "auto_detected")


def upgrade() -> None:
    """Drop every dead key from every ``kind='agent'`` config, writing back only
    the rows that actually carried one."""
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, config_json FROM resources WHERE kind = 'agent'")).all()
    for row_id, raw in rows:
        try:
            cfg = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if not isinstance(cfg, dict):
            continue
        if not any(key in cfg for key in _DEAD_FIELDS):
            continue
        for key in _DEAD_FIELDS:
            cfg.pop(key, None)
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(cfg), "id": row_id},
        )


def downgrade() -> None:
    """Deliberately a no-op — putting the keys back would re-create the bug.

    The usual shape for a field-strip migration (0032) restores the old
    defaults, because there the field removal shipped WITH the migration: one
    revision down is code that still declares the fields. That does not hold
    here. ``disable_native_memory`` left ``AgentConfig`` in #323 and
    ``auto_detected`` earlier still, both long before this revision, so the
    build at 0055 does not declare them either — it is the build this migration
    exists to unbreak. Writing ``disable_native_memory`` back into every row
    would hand that build exactly the row it answers 422 on.

    Stripping a key is not lossy in any way a downgrade could repair, either:
    nothing has read these values since the fields were removed.
    """
