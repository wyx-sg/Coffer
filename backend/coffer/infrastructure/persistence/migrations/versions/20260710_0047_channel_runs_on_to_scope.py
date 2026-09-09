"""channel runs_on config migrates to framework scope (ADR-045 amendment)

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-10

Spec 009 amendment: a channel's runtime affinity (which single machine's
runtime starts its adapter) was carried in `config_json.runs_on`
(ADR-043); it is now superseded by the framework-level machine x agent
`scope` column 0046 added (ADR-045). This migration backfills every
existing `kind='channel'` row's `scope_json` from its stored
`config_json.runs_on`:

  - runs_on: "<id>"  -> scope_json = '{"<id>": "*"}'  (bound to that machine)
  - runs_on: null    -> scope_json = '{}'             (ADR-043's "unbound
    runs nowhere" — an EMPTY scope object, deliberately NOT NULL: at the
    framework level NULL now means "unscoped / active everywhere", the
    opposite of a channel's historical off-by-default safety)

Only rows where `scope_json IS NULL` are touched, so the migration is
idempotent and never clobbers a scope already set (by a user, the REST
scope endpoint, or a prior partial run of this same migration).
`config_json.runs_on` itself is left untouched — the field stays in the
schema, inert (see coffer.domain.channel.config).

ResourceService.register() also gains a channel-kind default (`{}`, ADR-045
amendment) so a channel registered AFTER this migration starts dormant too,
matching this backfill rather than reverting to "active everywhere".

Migration scripts never import application code, so field names stay
inlined (mirrors 0037's `_migrate` pattern for `resources` row rewrites).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                "SELECT id, config_json FROM resources "
                "WHERE kind = 'channel' AND scope_json IS NULL"
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        try:
            cfg = json.loads(row["config_json"])
        except (TypeError, ValueError):
            cfg = None
        runs_on = cfg.get("runs_on") if isinstance(cfg, dict) else None
        scope = {runs_on: "*"} if runs_on else {}
        bind.execute(
            sa.text("UPDATE resources SET scope_json = :scope WHERE id = :id"),
            {"scope": json.dumps(scope), "id": row["id"]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE resources SET scope_json = NULL WHERE kind = 'channel'"))
