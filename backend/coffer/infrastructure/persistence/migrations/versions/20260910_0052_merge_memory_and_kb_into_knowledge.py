"""merge the memory and knowledge_base kinds into one `knowledge` kind

Revision ID: 0052
Revises: 0051
Create Date: 2026-09-10

Coffer had two resource kinds over one substrate. ``documents``, ``chunks``,
the FTS5 index and the vector index were always shared; only the facades were
two. This is the database half of collapsing them.

**The kinds merge.** ``memory`` and ``knowledge_base`` rows both become
``knowledge``. The scope a row denotes is read from its name — ``global``,
``project-<ULID>``, or a name the user chose — so nothing needs a new column to
say which of the three it is.

**The existing rows are removed rather than converted**, which is the part
worth explaining, because it is not merely tidying:

* ``memory:global`` and ``knowledge_base:global`` both existed. ``resources``
  is keyed by ``(kind, name)``, so converting both would collide, and any
  automatic rename would be a guess about which one the user meant.
* Every ``documents`` row was ``kind='memory'`` — the knowledge base was
  created 2026-06-22 and never held a document. There is no knowledge-base
  content to preserve.
* The memory content those rows indexed was the journal lane, removed with
  transcript distillation in 0050. The index would point at files that no
  longer exist.

So the index tables are cleared and re-accumulated by explicit writes and file
ingestion, which is what the files-as-truth design already assumes
(ADR files-as-truth-sqlite-retrieval): the index is derived, never the system
of record.

The two machine-local side tables are renamed, not dropped — a project root and
a display label describe a scope regardless of what the kind is called. Their
``store_name`` key column is renamed with them: the thing it names is a scope,
and the ORM models read it under that name.

Guarded throughout so a database missing any of these still upgrades.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect, text

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENAMES = (
    ("memory_store_project_roots", "knowledge_scope_project_roots"),
    ("memory_store_labels", "knowledge_scope_labels"),
)


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Drop the derived index. It described memory content that no longer
    #    exists, and it is rebuildable from the files by design.
    for table in ("chunks", "documents_fts", "documents"):
        if _has_table(table):
            bind.execute(text(f"DELETE FROM {table}"))

    # 2. Remove the old resource rows. See the module docstring for why this is
    #    a delete and not a conversion.
    if _has_table("resources"):
        bind.execute(text("DELETE FROM resources WHERE kind IN ('memory', 'knowledge_base')"))

    # 3. The side tables outlive the rename: they key on a scope name, which is
    #    unchanged, and they are machine-local so they never travel in a bundle.
    for old, new in _RENAMES:
        if _has_table(old) and not _has_table(new):
            op.rename_table(old, new)
        # The key column travels with the table: it names a scope now.
        if _has_column(new, "store_name") and not _has_column(new, "scope_name"):
            op.alter_column(new, "store_name", new_column_name="scope_name")


def downgrade() -> None:
    """Rename the side tables back. The deleted rows do not come back.

    They were a derived index over files that no longer exist and two resource
    rows that would collide on the way forward; recreating either would be
    inventing data, not restoring it.
    """
    for old, new in _RENAMES:
        if _has_column(new, "scope_name") and not _has_column(new, "store_name"):
            op.alter_column(new, "scope_name", new_column_name="store_name")
        if _has_table(new) and not _has_table(old):
            op.rename_table(new, old)
