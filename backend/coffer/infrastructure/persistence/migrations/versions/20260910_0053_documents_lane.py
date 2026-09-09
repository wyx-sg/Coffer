"""documents.lane: which of a scope's two writers owns an indexed row

Revision ID: 0053
Revises: 0052
Create Date: 2026-09-10

After the memory + knowledge_base merge a scope has two writers indexing into
one ``documents`` table under a single ``(kind, resource_name)``: the entry
reconciler over ``<scope>/knowledge/`` and the ingest scan over
``<scope>/inbox/``. Nothing in the row said which was which, so every document
read — the list, ``document_count``, the chunk counts — also returned entries.

The discriminator is stored rather than derived from ``path`` because the paths
genuinely overlap: an entry lives at ``<scope>/knowledge/inbox/<id>.md`` and an
ingested document at ``<scope>/inbox/<id>.md``, so any predicate matching
``inbox/`` catches both. Anchoring on the scope directory would also push
knowledge-lane layout into the kind-agnostic repository, which serves every
kind. A column keeps the row self-describing and the filter indexable.

Backfill keys on the entry lane's distinctive nesting, ``knowledge/inbox/``.
Matching the bare ``knowledge/`` segment would be wrong: the storage root is
itself ``~/.coffer/knowledge/``, so *every* absolute path contains it. In
practice the table is empty here — 0052 clears it one revision earlier — so
this matters only for a database that somehow carries rows across.

``inbox`` is the server default because ingestion is the writer that existed
before entries shared the table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "idx_documents_kind_res_lane"


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def _has_index(table: str, name: str) -> bool:
    if not _has_table(table):
        return False
    return any(i["name"] == name for i in inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if not _has_table("documents"):
        return

    if not _has_column("documents", "lane"):
        op.add_column(
            "documents",
            sa.Column("lane", sa.String(), nullable=False, server_default="inbox"),
        )
        # An entry sits at ``<scope>/knowledge/inbox/<id>.md``, an ingested
        # document at ``<scope>/inbox/<id>.md``. Anchor on the full two-segment
        # entry lane: the single segment ``knowledge/`` appears in every
        # absolute path, because the storage root is ``~/.coffer/knowledge/``.
        op.get_bind().execute(
            text(
                "UPDATE documents SET lane = 'knowledge' "
                "WHERE path LIKE '%/knowledge/inbox/%' OR path LIKE 'knowledge/inbox/%'"
            )
        )

    if not _has_index("documents", _INDEX):
        op.create_index(_INDEX, "documents", ["kind", "resource_name", "lane"])


def downgrade() -> None:
    if _has_index("documents", _INDEX):
        op.drop_index(_INDEX, table_name="documents")
    if _has_column("documents", "lane"):
        op.drop_column("documents", "lane")
