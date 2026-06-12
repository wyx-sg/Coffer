"""Virtual-table DDL for the substrate (FTS5 keyword index).

``documents_fts`` is an FTS5 virtual table — it has no ORM model, so
``Base.metadata.create_all`` would skip it. We hook ``after_create`` on the
``chunks`` table so any ``create_all`` (tests, fresh DBs) also builds the FTS5
table. The production path additionally runs the Alembic migration, which issues
the same DDL; ``IF NOT EXISTS`` keeps both idempotent.

``vec_chunks`` (sqlite-vec) is created lazily by ``VecIndex`` at the configured
embedding width, not here, because its column width is per-store.
"""

from __future__ import annotations

from sqlalchemy import DDL, event

from coffer.infrastructure.knowledge.models import ChunkModel

#: FTS5 index over chunk text. The text lives once inside the FTS index (it is
#: NOT duplicated into a base SQLite table). ``chunk_id`` UNINDEXED maps a hit
#: back to its ``chunks`` row; ``resource_name`` UNINDEXED scopes the search.
#: (A ``content=''`` contentless table cannot return its own column values, so
#: snippets would require reading the files — we keep the text in the FTS index
#: to serve passages directly.)
CREATE_DOCUMENTS_FTS = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5("
    "text, resource_name UNINDEXED, chunk_id UNINDEXED, "
    "tokenize='unicode61'"
    ")"
)

DROP_DOCUMENTS_FTS = "DROP TABLE IF EXISTS documents_fts"


event.listen(
    ChunkModel.__table__,
    "after_create",
    DDL(CREATE_DOCUMENTS_FTS),  # type: ignore[no-untyped-call]
)
event.listen(
    ChunkModel.__table__,
    "before_drop",
    DDL(DROP_DOCUMENTS_FTS),  # type: ignore[no-untyped-call]
)
