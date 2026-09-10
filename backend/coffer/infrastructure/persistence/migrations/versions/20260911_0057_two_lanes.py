"""documents.lane: rename the two lane values to notes / docs

Revision ID: 0057
Revises: 0056
Create Date: 2026-09-11

The knowledge substrate collapses to two lanes on disk. ``<scope>/knowledge/``
(with its nested ``knowledge/inbox/`` staging area) becomes ``<scope>/notes/``,
and ``<scope>/inbox/`` becomes ``<scope>/docs/``. The lanes ``rules/``,
``handoff/`` and ``superseded/``, along with ``consolidation-log.md`` and
``knowledge/INDEX.md``, are removed outright.

``documents.lane`` — added in 0053 to say which writer owns an indexed row —
therefore has to rename its two values with the directories they describe:
``knowledge`` → ``notes`` and ``inbox`` → ``docs``. The column's server default
moves with them.

This is a value rename, not a schema change, so it is written as two UPDATEs
rather than a table rebuild. The row's ``path`` still points at the OLD
directory afterwards; that is deliberate and harmless. The filesystem move runs
separately at daemon start (``infrastructure/knowledge_scope/lane_migration.py``),
and the lazy reindex-on-read that follows it re-derives every path from the
files actually on disk. Anchoring this migration on the stored path instead would
couple it to whether the daemon happened to reach the filesystem pass first.

No load-time shim survives this: nothing in the codebase reads or writes the
strings ``knowledge`` / ``inbox`` as a lane after this revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ``old lane value -> new lane value``, applied in both directions.
_RENAMES = (("knowledge", "notes"), ("inbox", "docs"))


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def _rename_values(pairs: Sequence[tuple[str, str]]) -> None:
    bind = op.get_bind()
    for old, new in pairs:
        bind.execute(
            text("UPDATE documents SET lane = :new WHERE lane = :old"),
            {"old": old, "new": new},
        )


def upgrade() -> None:
    if not _has_column("documents", "lane"):
        return
    _rename_values(_RENAMES)
    # ``alter_column`` on SQLite is a table rebuild via batch mode; the default
    # only matters for a row inserted by a writer that omits the column, and
    # every writer sets it explicitly. Kept in sync anyway so the schema does
    # not describe a lane that no longer exists.
    with op.batch_alter_table("documents") as batch:
        batch.alter_column(
            "lane",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default="docs",
        )


def downgrade() -> None:
    if not _has_column("documents", "lane"):
        return
    _rename_values([(new, old) for old, new in _RENAMES])
    with op.batch_alter_table("documents") as batch:
        batch.alter_column(
            "lane",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default="inbox",
        )
