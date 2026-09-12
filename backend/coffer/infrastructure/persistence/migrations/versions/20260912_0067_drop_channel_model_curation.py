"""take model curation back OFF every channel

A channel curates no models. It is a route to an agent, and the agent's own CLI
default is what a new conversation opens on while ``/model`` offers that agent's
whole catalogue and refuses nothing. The channel's ``default_model`` (what a
fresh conversation pinned) and ``models`` (the range ``/model`` could reach)
that 0063 moved here from the agent therefore have no reader left: the fields
are gone from ``ChannelConfig``, the binding no longer carries them, and the
``/model`` card starts from the agent's suggestions directly.

This is the whole of the cleanup: no load-time shim tolerates either key
anywhere, because a migration is one-shot and the data is corrected here rather
than worked around forever. (Pydantic ignores unknown keys, so an uncleaned row
would still validate — it would simply carry two dead keys around forever,
which is exactly what this revision exists to prevent.)

Idempotent: a row carrying neither key is skipped, so a re-run matches nothing.
The key names are inlined rather than imported — a migration must mean the same
thing forever, and importing the model would make this revision's behaviour
drift as the model evolves.

Revision ID: 0067
Revises: 0066
Create Date: 2026-09-12
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067"
down_revision: str | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The ``ChannelConfig`` keys this revision retires, frozen here.
_DEFAULT_MODEL = "default_model"
_MODELS = "models"


def _rewrite(add: bool) -> None:
    """Strip (or restore as uncurated) the two curation keys on every channel row."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'channel'")
    ).fetchall()
    for row_id, raw in rows:
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue  # a row the app cannot read either; not this script's to fix
        if not isinstance(config, dict):
            continue
        if add:
            if _DEFAULT_MODEL in config and _MODELS in config:
                continue
            config.setdefault(_DEFAULT_MODEL, None)
            config.setdefault(_MODELS, [])
        else:
            dropped_default = config.pop(_DEFAULT_MODEL, ...) is not ...
            dropped_models = config.pop(_MODELS, ...) is not ...
            if not dropped_default and not dropped_models:
                continue
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(config), "id": row_id},
        )


def upgrade() -> None:
    _rewrite(add=False)


def downgrade() -> None:
    """Put both keys back in their uncurated form — ``default_model`` unset and
    ``models`` the empty (no restriction) list — which is what every reader
    below this revision treats as "the agent's default, offer everything".
    Which model a channel had pinned, and which ids it had ticked, are not
    recoverable: nothing above reads them any more, so there was nothing to
    preserve."""
    _rewrite(add=True)
