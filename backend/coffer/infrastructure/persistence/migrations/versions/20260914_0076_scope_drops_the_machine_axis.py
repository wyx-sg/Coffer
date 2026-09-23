"""drop scope's machine axis: ``{"agents": a, "machines": m}`` -> ``{"agents": a}``

``resources.scope_json`` goes back to a single axis. A resource's activation
state is machine-local — it is set on the machine it applies to and does not
travel (spec vault-sync "Keep reach machine-local") — so each machine already
says which resources it activates by *holding* that scope. Naming machine ids
inside the scope as well recorded the same fact twice, with two places to
disagree, which is the counterpart 0072 added and this revision removes.

Dropping the key is not the same as removing the axis, and the difference is
the whole of this script. ``{"agents": null, "machines": ["x"]}`` was active on
machine ``x`` and nowhere else; delete ``machines`` and it reads as active for
every agent, everywhere. That is WIDENING — a resource silently exposed where
it was deliberately kept out — and it is the one direction a migration over
someone's live vault must never take. Narrowing is merely inconvenient: it is
visible on the page and one click undoes it.

So the machine axis is not dropped, it is RESOLVED, against the machine this
database belongs to:

- ``machines: null`` (unrestricted) — no machine was ever excluded, so the row
  keeps its agent axis verbatim. Nothing changes anywhere.
- ``machines: [...]`` and this machine's id is in the list — the row was active
  here subject only to its agent axis, so that axis alone says the same thing.
- anything else — an id not in the list, the empty list, a value that is not a
  list at all, or an id this script could not determine — the row was DORMANT
  here, and ``{"agents": []}`` is dormant under the new shape. Exactly what
  this machine saw, and never more.

This machine's id comes from ``daemon-config.json`` beside the database, which
is not a guess: it is the cache the running daemon itself read to evaluate
scope (``infrastructure.daemon.config.read_cached_machine_id``), so reading it
reproduces the answers this machine was actually giving. The directory is
derived from the Alembic bind's own database path rather than from ``HOME``, so
a vault opened from anywhere resolves against its own neighbour file. An absent,
unreadable or idless cache leaves the id unknown and takes the dormant branch —
a migration must never fail because a cache is missing, and a vault that cannot
say which machine it is has no claim to be on any allow-list.

Idempotent: a dict already lacking ``machines`` is left alone, so a re-run
matches nothing. The shape is inlined rather than imported from
``coffer.domain.scope`` — a migration must mean the same thing forever, and
importing the domain would make this revision drift as that module evolves.

``NULL`` (unscoped) stays ``NULL``, and a value that is not an object — a stale
pre-0072 list, or garbage — is left exactly as found; a row the app cannot read
either is not this script's to fix.

Revision ID: 0076
Revises: 0075
Create Date: 2026-09-14
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0076"
down_revision: str | None = "0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGENTS = "agents"
_MACHINES = "machines"
_DAEMON_CONFIG = "daemon-config.json"
_MACHINE_ID = "machine_id"


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


def _this_machine_id() -> str | None:
    """The id cached beside this database, or ``None`` when it cannot be read.

    Every failure collapses into ``None`` on purpose: no file, no permission,
    not JSON, not an object, no id, a blank id, or a database that has no
    directory to look in at all (``:memory:``) all mean the same thing — this
    script cannot say which machine it is, and must therefore not claim
    membership of any machine allow-list.
    """
    bind = op.get_bind()
    database = bind.engine.url.database
    if not database or database == ":memory:":
        return None
    try:
        payload = json.loads((pathlib.Path(database).parent / _DAEMON_CONFIG).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    cached = payload.get(_MACHINE_ID)
    if isinstance(cached, str) and cached.strip():
        return cached.strip()
    return None


def upgrade() -> None:
    """Resolve every machine axis away, preserving what this machine saw."""
    machine_id = _this_machine_id()
    for row_id, raw in _rows():
        try:
            scope = json.loads(raw)
        except (TypeError, ValueError):
            continue  # a row the app cannot read either; not this script's to fix
        if not isinstance(scope, dict) or _MACHINES not in scope:
            continue  # already single-axis (or not an object) — leave it be
        machines = scope.get(_MACHINES)
        if machines is None:
            _write(row_id, {_AGENTS: scope.get(_AGENTS)})  # unrestricted: nothing to resolve
        elif isinstance(machines, list) and machine_id is not None and machine_id in machines:
            _write(row_id, {_AGENTS: scope.get(_AGENTS)})  # named this machine: agents alone say it
        else:
            _write(row_id, {_AGENTS: []})  # dormant here, and dormant is what it stays


def downgrade() -> None:
    """Put an unrestricted machine axis back on every single-axis object.

    The machine lists themselves are gone — resolving them was the point, and
    an inverse cannot invent back a restriction the upgrade collapsed. ``null``
    is the only honest stand-in, and it is also the safe one: it WIDENS that
    axis, which is the direction that cannot make a resource vanish from a
    machine that could still see it. A row that already carries the key (never
    upgraded) is left alone, so this is idempotent too, and ``NULL`` stays
    ``NULL`` for the same reason it does on the way up.
    """
    for row_id, raw in _rows():
        try:
            scope = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(scope, dict) or _MACHINES in scope:
            continue
        _write(row_id, {_AGENTS: scope.get(_AGENTS), _MACHINES: None})
