"""take the curated ``models`` set back OFF every agent

Model curation moved from the AGENT to the CHANNEL (spec channels FR-071). An
agent answers one question — what can this agent be put on — and the answer is
its whole catalogue; who may pick from it is decided by the surface that has an
audience, and a channel now carries its own ``default_model`` plus an allowed
range. The per-agent ticked set 0060 introduced has no reader left: the
``GET|PUT /api/v1/agent-providers/{agent_key}/models/selection`` routes are gone
and ``AgentConfig`` forbids extra keys, so a row still carrying ``models`` would
fail to validate on load.

This is the whole of the cleanup: no load-time shim tolerates the key anywhere,
because a migration is one-shot and the data is corrected here rather than
worked around forever.

Idempotent: a row without ``models`` is skipped, so a re-run matches nothing.
The key name is inlined rather than imported — a migration must mean the same
thing forever, and importing the model would make this revision's behaviour
drift as the model evolves.

Revision ID: 0062
Revises: 0061
Create Date: 2026-09-12
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The ``AgentConfig`` key this revision retires, frozen here.
_KEY = "models"


def _rewrite(add: bool) -> None:
    """Strip (or restore as empty) ``models`` on every readable agent row."""
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
        if add:
            if _KEY in config:
                continue
            config[_KEY] = []
        elif config.pop(_KEY, ...) is ...:
            continue
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(config), "id": row_id},
        )


def upgrade() -> None:
    _rewrite(add=False)


def downgrade() -> None:
    """Put the key back as the empty (uncurated) list, which is what 0060 wrote
    and what every reader below this revision treats as "offer everything".
    Which models a user had ticked is not recoverable — nothing above reads it
    any more, so there was nothing to preserve."""
    _rewrite(add=True)
