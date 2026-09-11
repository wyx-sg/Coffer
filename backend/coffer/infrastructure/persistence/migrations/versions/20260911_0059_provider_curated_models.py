"""give every connection its curated ``models`` set, empty = unrestricted

A connection now records WHICH of its endpoint's models it offers downstream
(spec provider-switching amendment 2026-09-11). The chosen model still lives at the point of
use — this list only narrows the menu every picker shows.

Every connection written before this revision has no answer to that question in
its ``config_json``. The answer they should get is "no restriction": they were
created when the endpoint's whole catalogue was on offer, and an upgrade must
not quietly hide models a user was already picking from. That is the empty
list, which this revision writes into each row so the stored config states its
own answer rather than leaning on a reader's default — the same one-shot rule
0056 followed when it took two keys OUT.

Idempotent: a row that already carries ``models`` is skipped, so a re-run
matches nothing. The key name is inlined rather than imported — a migration
must mean the same thing forever, and importing the model would make this
revision's behaviour drift as the model evolves.

Revision ID: 0057
Revises: 0056
Create Date: 2026-09-11
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The ``ProviderConfig`` key this revision introduces, frozen here.
_KEY = "models"


def _rewrite(add: bool) -> None:
    """Add (or strip) ``models`` on every readable ``kind='provider'`` row."""
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
    _rewrite(add=True)


def downgrade() -> None:
    """Drop the key again — the pre-0057 ``ProviderConfig`` forbids it. Which
    models a user had curated is not recoverable, and nothing below reads it."""
    _rewrite(add=False)
