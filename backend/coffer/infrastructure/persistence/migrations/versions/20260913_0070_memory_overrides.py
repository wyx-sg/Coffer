"""the developer's decisions about a fact — the one table memory adds

Revision ID: 0067
Revises: 0066
Create Date: 2026-09-12

Spec memory FR-040/FR-070, ADR ``aggregate-agent-memory-never-write-it``.
Everything under ``~/.coffer/memory/`` is a file aggregation can delete and
rebuild; the developer's hide/pin/supersede/settle decisions are the one
thing that is not, so they get the one table this layer is allowed to add.

Keyed by ``fact_key`` — ``Fact.key``, derived from the fact's origins — rather
than a surrogate id, because that identity is built to survive a rebuild that
renames or regroups every file underneath it (FR-022, FR-041).

Guarded so a database that somehow already has this table upgrades cleanly,
matching every other migration in this file.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0070"
down_revision: str | None = "0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "memory_overrides"


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("fact_key", sa.String(), primary_key=True),
        sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("superseded_by", sa.String(), nullable=False, server_default=""),
        sa.Column("conflict_choice", sa.String(), nullable=False, server_default=""),
        sa.Column("actor", sa.String(), nullable=False, server_default="system"),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop the table. The developer's decisions are lost with it — recording
    them again is the way back, same as every override-holding table here."""
    if _has_table(_TABLE):
        op.drop_table(_TABLE)
