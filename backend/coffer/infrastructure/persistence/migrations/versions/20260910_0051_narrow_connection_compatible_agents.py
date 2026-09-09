"""narrow connection compatible_agents to claude_code and codex

Revision ID: 0051
Revises: 0050
Create Date: 2026-09-10

Revision 0048 deleted the ``kind='agent'`` rows carrying the four removed types
(``cursor`` / ``opencode`` / ``openclaw`` / ``hermes``), but the same names also
live INSIDE ``kind='provider'`` rows, in ``config_json -> compatible_agents``:
the list of agent types a connection may project into. Those were left behind,
and ``ProviderConfig`` forbids them — so on a real install the very first
``ProviderConfig.model_validate`` after the upgrade raises, and a connection
that had been working for months becomes unreadable. Found on a live machine,
where the ACTIVE connection carried
``["codex", "opencode", "hermes", "openclaw", "claude_code"]`` and would have
taken the LLM-connections page and the Codex key lookup down with it.

Removed names are dropped and the surviving ones kept in order. A connection
left with nothing is set back to ``null``, which means "the default for this
wire" — the same state it would have had if the user had never narrowed it, and
the only alternative to an empty list that reaches no agent at all.

Idempotent: a second run matches no rows. Migration scripts never import
application code, so the removed values are inlined here and stay frozen as the
model evolves.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Frozen copies of the two type sets, so this script never imports the model.
_REMOVED = ("cursor", "opencode", "openclaw", "hermes")
_KEPT = ("claude_code", "codex")


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'provider'")
    ).fetchall()
    for row_id, raw in rows:
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue  # a row the app cannot read either; not this script's to fix
        if not isinstance(config, dict):
            continue
        agents = config.get("compatible_agents")
        if not isinstance(agents, list):
            continue
        kept = [a for a in agents if a in _KEPT]
        if kept == agents:
            continue
        # Everything the user chose is gone: fall back to the wire default
        # rather than persisting a list that projects into nothing.
        config["compatible_agents"] = kept or None
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(config), "id": row_id},
        )


def downgrade() -> None:
    # Lossy by nature: which removed types a connection once listed is not
    # recoverable, and no agent of those types can exist to project into.
    pass
