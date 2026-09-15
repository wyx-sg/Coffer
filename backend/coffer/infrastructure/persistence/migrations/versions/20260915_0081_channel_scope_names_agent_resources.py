"""rewrite a channel's scope from agent keys into agent resource names

A channel's ``scope`` names the agents it may drive, and it names them the way
every other kind's scope does — by agent RESOURCE name, which is what the reach
control offers and what the resource table holds. Its ``default_agent`` is an
agent KEY (``claude_code``), because that is what the turn platform routes on.

Until now the three places that compared them did so directly, so the value a
channel's scope could actually hold was the agent key: every real resource name
was refused on the way in, and the key was the only string that passed. Reading
the comparison in one vocabulary fixes the refusal — and turns those stored
keys into names this vault does not hold, which would take the channel dark on
upgrade. So they are translated here, once, at the moment the reader changes.

Each stored entry is kept as-is when an agent resource already goes by that
name. Otherwise, if it matches a registered agent's ``type``, it is replaced by
the name(s) of the resource(s) of that type — two Claude Code agents registered
against different config dirs both become reachable, which is what naming the
type meant. Anything else is left exactly as found: it names neither a resource
nor a type this vault knows, so there is nothing to translate it into and
guessing would widen a reach the owner narrowed.

Revision ID: 0081
Revises: 0080
Create Date: 2026-09-15
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0081"
down_revision: str | None = "0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Where an agent resource keeps its key. Inlined rather than imported, as
#: 0077-0080 were: a migration must keep meaning the same thing after the
#: constant it was written against moves.
_TYPE = "type"


def _agents() -> tuple[set[str], dict[str, list[str]]]:
    """Registered agent resource names, and the names of each agent key."""
    bind = op.get_bind()
    names: set[str] = set()
    by_key: dict[str, list[str]] = {}
    for name, raw in bind.execute(
        sa.text("SELECT name, config_json FROM resources WHERE kind = 'agent'")
    ).fetchall():
        names.add(name)
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(config, dict) and isinstance(config.get(_TYPE), str):
            by_key.setdefault(config[_TYPE], []).append(name)
    return names, by_key


def _translated(agents: list[Any], names: set[str], by_key: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for entry in agents:
        if not isinstance(entry, str):
            continue
        if entry in names:
            out.append(entry)
        else:
            out.extend(by_key.get(entry, [entry]))
    return sorted(set(out))


def upgrade() -> None:
    """Translate every channel scope written in the old vocabulary."""
    bind = op.get_bind()
    names, by_key = _agents()
    if not names:
        return  # nothing registered to translate against
    rows = bind.execute(
        sa.text("SELECT id, scope_json FROM resources WHERE kind = 'channel'")
    ).fetchall()
    for row_id, raw in rows:
        if not raw:
            continue
        try:
            scope = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(scope, dict) or not isinstance(scope.get("agents"), list):
            continue
        agents = scope["agents"]
        if not agents:
            continue  # dormant: the owner switched it off, and off stays off
        translated = _translated(agents, names, by_key)
        if translated == agents:
            continue
        bind.execute(
            sa.text("UPDATE resources SET scope_json = :scope WHERE id = :id"),
            {"scope": json.dumps({**scope, "agents": translated}, sort_keys=True), "id": row_id},
        )


def downgrade() -> None:
    """Nothing to undo.

    Below this revision the comparison is the direct one, so a scope holding a
    resource name is a scope that drives nothing — and putting the agent key
    back would silently re-narrow a reach that now reads correctly. A vault
    rolled back is better served by the value it can still read.
    """
