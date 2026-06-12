"""rekey chunk ids per store (cross-store chunk-id collision)

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-12

Document ids are content-addressed (sha256[:16] of the file content), so the
same file ingested into two stores repeats its document id. ``chunks.id`` was
the bare ``'<doc-id>:<position>'`` under a single-column PK, and the chunk/FTS
writes filtered by ``document_id`` only — so ingesting the same file into a
second KB stole/re-tagged the first KB's chunk + FTS rows, and deleting the
document from either KB wiped the other's chunks (the first KB's search
silently returned nothing).

The fix namespaces every chunk id with a 12-hex digest of the owning
``(kind, resource_name)`` store: ``'<digest>:<doc-id>:<position>'`` (see
``store_scope`` in ``coffer/infrastructure/knowledge/sqlite_index.py``). This
revision rekeys existing rows in place — ``documents_fts.chunk_id`` first (it
joins on the old ids), then ``chunks.id``. The per-store sqlite-vec tables keep
the bare ids (their table NAME already namespaces the store), so no vec rebuild
is needed. Rows a past collision already corrupted cannot be recovered here:
files are the source of truth and ``reindex`` rebuilds them.

Idempotent: only old-format ids (``document_id || ':' || position``) are
touched, so a re-run (or a DB stamped mid-migration) converges.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _store_scope(kind: str, resource_name: str) -> str:
    # Mirrors coffer.infrastructure.knowledge.sqlite_index.store_scope —
    # inlined because migration scripts never import application code (they
    # must stay frozen as the code evolves).
    return hashlib.sha1(f"{kind}\x00{resource_name}".encode()).hexdigest()[:12]


def upgrade() -> None:
    bind = op.get_bind()
    stores = bind.execute(sa.text("SELECT DISTINCT kind, resource_name FROM chunks")).all()
    for kind, resource_name in stores:
        scope = _store_scope(str(kind), str(resource_name))
        # FTS rows first: the mapping to chunks rows is via the OLD ids.
        bind.execute(
            sa.text(
                "UPDATE documents_fts SET chunk_id = :scope || ':' || chunk_id "
                "WHERE chunk_id IN ("
                "SELECT id FROM chunks WHERE kind = :kind AND resource_name = :rn "
                "AND id = document_id || ':' || position)"
            ),
            {"scope": scope, "kind": kind, "rn": resource_name},
        )
        bind.execute(
            sa.text(
                "UPDATE chunks SET id = :scope || ':' || id "
                "WHERE kind = :kind AND resource_name = :rn "
                "AND id = document_id || ':' || position"
            ),
            {"scope": scope, "kind": kind, "rn": resource_name},
        )


def downgrade() -> None:
    # No reverse rekey: stripping the prefix would reintroduce the cross-store
    # PK collision this revision exists to fix (the same doc in two stores).
    # Pre-0017 code reads chunk ids opaquely (via document_id filters and the
    # FTS join), so the namespaced ids remain fully usable after a downgrade.
    pass
