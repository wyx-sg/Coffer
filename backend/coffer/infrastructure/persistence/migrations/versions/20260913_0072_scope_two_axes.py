"""give scope a machine axis: ``["a","b"]`` -> ``{"agents": ["a","b"], "machines": null}``

``resources.scope_json`` stopped being a bare list of agent names. It is now an
object with two independent allow-lists, ``AND``-ed — ``agents`` and
``machines`` — each ``null`` meaning unrestricted (spec vault-sync, "Scope
gains a machine axis").

Every existing row migrates by ADDITION: an agent list keeps exactly the agents
it named, and gains ``machines: null``, which is unrestricted. No resource's
effective activation changes, on this machine or any other — the point of the
null axis is that it reproduces today's behaviour exactly.

``NULL`` (unscoped) stays ``NULL``: there is no axis to add to a resource that
was never scoped, and writing ``{"agents": null, "machines": null}`` would say
the same thing in more bytes.

Idempotent: a row already carrying the object shape is left alone, so a re-run
matches nothing. The shape is inlined rather than imported from
``coffer.domain.scope`` — a migration must mean the same thing forever, and
importing the domain would make this revision drift as that module evolves.

Revision ID: 0072
Revises: 0071
Create Date: 2026-09-13
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0072"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGENTS = "agents"
_MACHINES = "machines"


def _rows() -> list[tuple[int, str]]:
    bind = op.get_bind()
    return [
        (row[0], row[1])
        for row in bind.execute(
            sa.text("SELECT id, scope_json FROM resources WHERE scope_json IS NOT NULL")
        ).fetchall()
    ]


def _write(row_id: int, value: Any) -> None:
    """Set one row's ``scope_json``; ``None`` writes SQL NULL (unscoped)."""
    op.get_bind().execute(
        sa.text("UPDATE resources SET scope_json = :scope WHERE id = :id"),
        {"scope": None if value is None else json.dumps(value), "id": row_id},
    )


def upgrade() -> None:
    """Wrap every agent list in the two-axis object."""
    for row_id, raw in _rows():
        try:
            scope = json.loads(raw)
        except (TypeError, ValueError):
            continue  # a row the app cannot read either; not this script's to fix
        if not isinstance(scope, list):
            continue  # already an object (or something else) — leave it be
        _write(row_id, {_AGENTS: scope, _MACHINES: None})


def downgrade() -> None:
    """Unwrap back to the bare agent list.

    A machine axis has nowhere to go in the old shape, so a row that named
    machines loses that restriction: downgrading WIDENS, which is the direction
    that cannot make a resource vanish from a machine that could still see it.
    For the same reason an unrestricted agent axis (``agents: null``) goes back
    to SQL NULL — the old shape's own way of saying "every agent" — rather than
    to ``[]``, which meant the opposite.
    """
    for row_id, raw in _rows():
        try:
            scope = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(scope, dict):
            continue  # already a list — nothing to unwrap
        agents = scope.get(_AGENTS)
        _write(row_id, agents if isinstance(agents, list) else None)
