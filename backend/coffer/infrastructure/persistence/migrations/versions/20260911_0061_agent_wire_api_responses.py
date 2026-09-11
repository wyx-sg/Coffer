"""flip agents' wire_api from "chat" to "responses"

Revision ID: 0061
Revises: 0060
Create Date: 2026-09-11

``wire_api = "chat"`` is not merely stale: Codex 0.139.0 refuses to load
``config.toml`` at all when it sees it — ``wire_api = "chat" is no longer
supported``, with ``responses`` named as the fix — so an agent Coffer projected
with that value has a CLI that will not start. ``AgentConfig`` now rejects the
value at the boundary, which stops new ones; this fixes the rows that already
carry it.

Revision 0037 did the same flip when ``wire_api`` lived on the CONNECTION.
Revision 0040 then moved the field off connections onto the agent, where it has
been settable through ``PATCH /api/v1/agents/{name}`` ever since — and that path
accepted ``"chat"`` right up to this change. So the rows this touches are agent
rows, and 0037 did not cover them.

Flipping rather than stripping: ``"responses"`` is what the value MEANT to
express (use Codex's Responses API) and is the only wire Codex still speaks, so
the setting survives as the one thing it can now say. The on-disk
``config.toml`` is only rewritten when a connection is (re)activated; this fixes
the stored value so the next projection writes config Codex accepts.

Migration scripts never import application code, so the field names stay
inlined.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEAD = "chat"
_LIVE = "responses"


def _remap(config_json: str, frm: str, to: str) -> str | None:
    """Return updated config JSON when this agent's ``wire_api`` equals ``frm``;
    otherwise ``None`` (nothing to write). A row whose config no longer parses is
    left alone — a migration is not the place to guess at a broken document."""
    try:
        cfg = json.loads(config_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(cfg, dict) or cfg.get("wire_api") != frm:
        return None
    cfg["wire_api"] = to
    return json.dumps(cfg)


def _flip(frm: str, to: str) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'agent'")
    ).fetchall()
    for row_id, config_json in rows:
        updated = _remap(config_json, frm, to)
        if updated is None:
            continue
        conn.execute(
            sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
            {"cfg": updated, "id": row_id},
        )


def upgrade() -> None:
    _flip(_DEAD, _LIVE)


def downgrade() -> None:
    """Restore the dead value on the way down.

    It is the honest inverse — the rows this touched are exactly the ones that
    said ``chat`` before — even though the value it restores is one Codex will
    not load. A downgrade returns the data to what the earlier revision
    described; it does not promise the result works with today's CLI.
    """
    _flip(_LIVE, _DEAD)
