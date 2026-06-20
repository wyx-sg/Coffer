"""documents.embed_pending: decouple content_sha256 from embed-retry state (KB8)

Revision ID: 0035
Revises: 0034
Create Date: 2026-06-21

The unified ``documents`` table previously overloaded ``content_sha256`` to
signal a degraded embed: when the embedding provider was unavailable the reindex
routine stored an EMPTY-STRING sentinel so the next reconcile would mismatch and
retry the embed. That broke the no-op gate (``new_sha == previous_sha`` never
held for a degraded doc, so every scan re-chunked + rewrote FTS for the whole
degraded corpus) and corrupted the files-as-truth sha.

This migration adds a dedicated ``embed_pending`` boolean so ``content_sha256``
can always carry the real body hash. The backfill is safe because ``''`` was
ONLY ever the degrade sentinel: any row whose stored sha is empty is a doc whose
embed is still pending, so it is migrated to ``embed_pending = 1`` (the next
reindex recomputes the real sha for it).

Idempotent on an empty table. Reversible (drops the column).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    # Guarded so the roundtrip suite (which stamps back and replays the chain
    # tail) can re-run this idempotently without a duplicate-column error.
    if not _has_column("documents", "embed_pending"):
        op.add_column(
            "documents",
            sa.Column("embed_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    # ``''`` was only ever the degrade sentinel — those rows are pending an embed.
    op.execute("UPDATE documents SET embed_pending = 1 WHERE content_sha256 = ''")


def downgrade() -> None:
    if _has_column("documents", "embed_pending"):
        op.drop_column("documents", "embed_pending")
