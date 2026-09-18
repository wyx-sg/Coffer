"""The attempt ceiling belongs to the task, and there is no token budget.

A workflow used to carry two run-wide numbers: one ceiling for every task's
attempts and one token budget that paused the run. Both were the wrong shape.
The drafting task that is cheap to re-run and the deploy task that must not be
tried twice shared a cap that was wrong for one of them, and a budget that
stopped a delivery three tasks from done stopped it for a reason nobody had
decided — it is a number of tokens, not a judgement about the work.

So ``attempt_ceiling`` moves down: onto every task, and onto every feedback
edge, because the work an edge creates is an ad-hoc task that exists nowhere
else in the template (spec workflow, FR-026). ``token_budget`` is gone.

This rewrites the two places a template is stored. A `workflow` resource's
config is the editable one. A run's ``template_snapshot`` is the frozen copy it
executes (FR-010), and it must be rewritten too: the parser now REFUSES a root
``token_budget`` as an unknown field, so a snapshot left alone would strand the
run that froze it — unreadable by the advancer and nameless in the list.

Every task inherits the ceiling its template had, so no run changes behaviour.
A task that somehow already carried its own keeps it.

``run.budget_exceeded`` events go with the concept. Folding one now raises, so
a run holding one could not be projected at all; there is no released build
that could have written one outside a developer's own vault, and leaving a row
nothing can read would be worse than dropping it.

Revision ID: 0091
Revises: 0090
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

_DEFAULT_CEILING = 3


def _moved_down(template: Any) -> dict[str, Any] | None:
    """The same template with the ceiling pushed onto tasks and edges.

    ``None`` when there is nothing to do, so a row that is already in the new
    shape is left byte-for-byte alone rather than reserialised.
    """
    if not isinstance(template, dict):
        return None
    if "attempt_ceiling" not in template and "token_budget" not in template:
        return None
    ceiling = template.get("attempt_ceiling")
    if not isinstance(ceiling, int) or isinstance(ceiling, bool) or ceiling < 1:
        ceiling = _DEFAULT_CEILING

    out = {k: v for k, v in template.items() if k not in ("attempt_ceiling", "token_budget")}
    stages = out.get("stages")
    if isinstance(stages, list):
        out["stages"] = [
            stage
            if not isinstance(stage, dict)
            else {
                **stage,
                "nodes": [
                    node if not isinstance(node, dict) else {"attempt_ceiling": ceiling, **node}
                    for node in stage.get("nodes", [])
                ]
                if isinstance(stage.get("nodes"), list)
                else stage.get("nodes"),
            }
            for stage in stages
        ]
    edges = out.get("edges")
    if isinstance(edges, list):
        out["edges"] = [
            edge if not isinstance(edge, dict) else {"attempt_ceiling": ceiling, **edge}
            for edge in edges
        ]
    return out


def _rewrite(table: str, id_col: str, json_col: str, *, where: str = "") -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT {id_col}, {json_col} FROM {table} {where}")).fetchall()
    for row_id, raw in rows:
        if raw is None:
            continue
        try:
            template = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            # A config this build cannot read is one this migration must not
            # guess at; the row is left exactly as it was found.
            continue
        moved = _moved_down(template)
        if moved is None:
            continue
        bind.execute(
            sa.text(f"UPDATE {table} SET {json_col} = :value WHERE {id_col} = :id"),
            {"value": json.dumps(moved), "id": row_id},
        )


def upgrade() -> None:
    _rewrite("resources", "id", "config_json", where="WHERE kind = 'workflow'")
    _rewrite("workflow_runs", "id", "template_snapshot")
    op.execute(sa.text("DELETE FROM workflow_events WHERE event_type = 'run.budget_exceeded'"))


def downgrade() -> None:
    # One-way on purpose. Going back would have to pick ONE ceiling for a
    # template whose tasks may now hold several, and the budget it would
    # restore has no value to restore it to.
    pass
