"""FTS5 keyword tokenizer: unicode61 -> trigram (KB1, CJK keyword search)

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-20

The keyword index ``documents_fts`` used the ``unicode61`` tokenizer, which does
not segment CJK text: Chinese has no word-boundary spaces, so a whole run becomes
one token and a query like ``向量检索`` never matched. Switch to the ``trigram``
tokenizer, which indexes 3-character sequences and so matches CJK (and arbitrary
substrings). Queries shorter than 3 characters fall back to a LIKE scan in the
index layer (``sqlite_index.keyword_search``).

An FTS5 tokenizer cannot be altered in place, so the table is recreated. The
chunk text lives only inside this FTS index (it is not duplicated into a base
table), so we copy every row through the rebuild rather than re-reading the
markdown files — no re-chunk, no re-embed, the sqlite-vec rows are untouched.

Idempotent on an empty table (no rows to copy). Reversible (trigram ->
unicode61). Keep the CREATE in sync with ``infrastructure/knowledge/ddl.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE = (
    "CREATE VIRTUAL TABLE documents_fts USING fts5("
    "text, resource_name UNINDEXED, chunk_id UNINDEXED, "
    "tokenize='{tokenize}'"
    ")"
)


def _rebuild(tokenize: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT text, resource_name, chunk_id FROM documents_fts")).all()
    op.execute("DROP TABLE IF EXISTS documents_fts")
    op.execute(_CREATE.format(tokenize=tokenize))
    for text_value, resource_name, chunk_id in rows:
        bind.execute(
            sa.text(
                "INSERT INTO documents_fts(text, resource_name, chunk_id) VALUES (:t, :rn, :cid)"
            ),
            {"t": text_value, "rn": resource_name, "cid": chunk_id},
        )


def upgrade() -> None:
    _rebuild("trigram")


def downgrade() -> None:
    _rebuild("unicode61")
