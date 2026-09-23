"""A workflow template's stored config stops carrying routes between stages.

``edges`` — a route from a later stage back to an earlier one — is gone from the
template (spec workflow "Send work back by the developer's hand, never a
template route"). A finding in a later task is acted on by the developer
retrying the task that was wrong or adding one that fixes it, because whether a
failing test means redo the code or redo the design is a judgement only whoever
holds the finding can make, and an edge drawn when the template was written
makes it in advance and for every run alike.

This is a stripping migration rather than a shim, and it is not optional.
``parse_template`` now REFUSES a config carrying ``edges`` as an unknown field,
which is the right failure for a template being written and the wrong one for a
template already stored: a workflow registered before this release would stop
opening — and a run executing its frozen snapshot would stall — with a refusal
naming a field the developer never typed. So the key is removed here, in the
two places a template's JSON lives:

* ``resources.config_json`` for every row of kind ``workflow`` — the template
  the developer edits and runs from;
* ``workflow_runs.template_snapshot`` — the copy a run froze at creation
  ("Freeze the template when a run is created"), which is what it actually
  executes and is therefore the one that would strand a run in flight rather
  than merely a menu entry.

Both are rewritten only when the key is present, so running this twice is a
no-op and a row written by some other build is left alone rather than guessed
at.

**The downgrade does not put the routes back, and cannot.** The edges were
data, not a derivation: nothing else in the row records where a route pointed,
so re-adding an empty ``edges`` list would restore the SHAPE while losing every
route it held — a template that looks migrated and has quietly forgotten what
it was for. Leaving the key absent is honest: an older build reads a template
with no routes, which is a template that never had any, and that is exactly
what this one is now.

Revision ID: 0103
Revises: 0102
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision: str = "0103"
down_revision: str | None = "0102"
branch_labels: str | None = None
depends_on: str | None = None

logger = logging.getLogger(__name__)

_KEY = "edges"


def _without_routes(raw: str | None) -> str | None:
    """``raw`` with its top-level ``edges`` removed, or ``None`` to leave it.

    ``None`` for anything this migration has no business touching: a null
    column, text that is not JSON, or a document that never had the key. A
    migration that rewrote a row it could not read would turn a config it did
    not understand into one it had definitely broken.
    """
    if not raw:
        return None
    try:
        config = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(config, dict) or _KEY not in config:
        return None
    config.pop(_KEY)
    return json.dumps(config)


def _strip(table: str, column: str, where: str) -> int:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT id, {column} FROM {table} WHERE {where}")).fetchall()
    changed = 0
    for row_id, raw in rows:
        rewritten = _without_routes(raw)
        if rewritten is None:
            continue
        conn.execute(
            sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id"),
            {"value": rewritten, "id": row_id},
        )
        changed += 1
    return changed


def upgrade() -> None:
    templates = _strip("resources", "config_json", "kind = 'workflow'")
    snapshots = _strip("workflow_runs", "template_snapshot", "1 = 1")
    # Counted and logged because zero is the expected answer on almost every
    # vault — the layer shipped days before this — and a silent zero is
    # indistinguishable from a migration that matched nothing because its WHERE
    # was wrong.
    logger.info("migration.0103.routes_stripped; templates=%d snapshots=%d", templates, snapshots)


def downgrade() -> None:
    """Deliberately empty. See the module docstring: the routes were data, and
    restoring an empty list would be a lie in the shape of a fix."""
