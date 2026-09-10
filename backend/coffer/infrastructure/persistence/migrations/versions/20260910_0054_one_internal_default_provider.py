"""enforce the single internal-default provider invariant (spec provider-switching FR-021)

FR-021 says at most one connection carries ``internal_default=true`` — it names
the connection Coffer's own LLM engine runs on, and "the internal engine" is
singular. ``ProviderService.set_internal_default`` upholds it by clearing every
other flag before setting this one, but that is the only path that does. A
config written straight through the generic resource-update route, the CLI's
``provider edit``, or a hand-edited row bypasses it entirely — and a live vault
was found holding **two** true, which makes "which connection does the internal
engine use?" a question with no defined answer.

The guard is a partial unique index rather than application validation, so it
covers every writer including a future one. SQLite indexes the ``kind`` column
under a predicate that admits only true-flagged provider rows, which makes "two
such rows" unrepresentable.

The normalisation before it keeps the most recently updated flagged row, on the
same reasoning migration 0036 used for the same field: the last write is the
one the user most plausibly meant.

Revision ID: 0054
Revises: 0053
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | None = None
depends_on: str | None = None

_INDEX = "ux_provider_single_internal_default"
_FLAGGED = "json_extract(config_json, '$.internal_default') = 1"


def upgrade() -> None:
    bind = op.get_bind()

    # Normalise first — the index cannot be created over data that violates it.
    flagged = (
        bind.execute(
            sa.text(
                f"SELECT name FROM resources WHERE kind = 'provider' AND {_FLAGGED} "
                "ORDER BY updated_at DESC, id DESC"
            )
        )
        .scalars()
        .all()
    )
    for name in list(flagged)[1:]:
        bind.execute(
            sa.text(
                "UPDATE resources "
                "SET config_json = json_set(config_json, '$.internal_default', json('false')) "
                "WHERE kind = 'provider' AND name = :name"
            ),
            {"name": name},
        )

    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX} ON resources (kind) "
        f"WHERE kind = 'provider' AND {_FLAGGED}"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
