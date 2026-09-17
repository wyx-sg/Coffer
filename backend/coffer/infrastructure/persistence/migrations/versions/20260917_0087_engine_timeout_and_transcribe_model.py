"""Coffer's own model gains a configurable bound, and speech-to-text its own model.

Two columns on the engine's singleton, both nullable, both meaning "the
built-in default" while unset — so this migration changes no vault's behaviour
on its own.

``model_timeout_s`` was a constant compiled into each call site: 60 seconds in
the distil pass, 20 in knowledge ingestion, none at all on curation's turns.
The right number is a property of the operator's endpoint, and against a slow
one the compiled-in bound made the passes fail in their most misleading mode —
gracefully, deferring work to the next pass while reporting success.

``transcribe_model`` was the environment variable ``COFFER_TRANSCRIBE_MODEL``,
read inside the daemon. The daemon is spawned detached by whichever surface
first needs one and inherits THAT caller's environment, so a value exported in
a shell profile never reached it and the model was, in a packaged install,
unchangeable. There is nothing to migrate from: an environment variable leaves
no row, and a vault that set one gets the same default it had.

The third change is the invariant behind the new ``transcribe_default`` flag.
``ProviderService.set_transcribe_default`` clears every other flag before
setting one, but that is the only path that does — a config written through the
generic resource-update route, or an incoming synced document, bypasses it.
Migration 0054 added a partial unique index for ``internal_default`` for
exactly this reason, and only AFTER a live vault was found holding two flagged
connections; the same index is created here rather than waiting for the same
discovery a second time. Nothing needs normalising first: the flag is new, so
no row can carry it yet.

Revision ID: 0087
Revises: 0086
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None

_TABLE = "internal_engine_config"

_INDEX = "ux_provider_single_transcribe_default"
_FLAGGED = "json_extract(config_json, '$.transcribe_default') = 1"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("model_timeout_s", sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column("transcribe_model", sa.String(), nullable=True))
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX} ON resources (kind) "
        f"WHERE kind = 'provider' AND {_FLAGGED}"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
    op.drop_column(_TABLE, "transcribe_model")
    op.drop_column(_TABLE, "model_timeout_s")
