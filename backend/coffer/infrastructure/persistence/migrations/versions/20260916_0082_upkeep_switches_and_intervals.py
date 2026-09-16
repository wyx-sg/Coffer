"""give every unattended pass a switch and a timer the operator can see

Coffer runs three passes on its own behalf: aggregation reads the agents' own
memory into the derived tree (spec memory FR-007), organise lets the model
rewrite that derived digest (spec memory FR-017), and tidy lets it rewrite the
user's own knowledge files (spec knowledge FR-031). Only the third had a switch,
and it had no surface — it could be changed by editing the synced settings
document and no other way. None of the three had a configurable interval: the
timers were constants compiled into the workers, so a vault that wanted
aggregation every ten minutes, or tidy once a week, could not say so.

This adds the two missing switches and all three intervals to the singleton
row that already holds ``auto_tidy_enabled``.

An interval of NULL means "this pass's own default". The default therefore
stays in one place — the worker that owns the pass — rather than being copied
into every vault at upgrade time, where raising it later would reach none of
them.

The two new switches default ON, matching the behaviour every vault has right
now: both passes already run unattended, and neither rewrites anything but
derived files that deleting and re-running reproduces. Only tidy, which
rewrites the user's own writing, ships off — and it stays exactly as the vault
has it.

Revision ID: 0082
Revises: 0081
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0082"
down_revision: str | None = "0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "internal_engine_config"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "auto_aggregate_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(_TABLE, sa.Column("aggregate_interval_s", sa.Integer(), nullable=True))
    op.add_column(
        _TABLE,
        sa.Column(
            "auto_organise_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(_TABLE, sa.Column("organise_interval_s", sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column("tidy_interval_s", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "tidy_interval_s")
    op.drop_column(_TABLE, "organise_interval_s")
    op.drop_column(_TABLE, "auto_organise_enabled")
    op.drop_column(_TABLE, "aggregate_interval_s")
    op.drop_column(_TABLE, "auto_aggregate_enabled")
