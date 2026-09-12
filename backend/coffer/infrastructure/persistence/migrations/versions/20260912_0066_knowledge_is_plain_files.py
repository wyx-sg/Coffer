"""knowledge becomes a directory of files: rewrite the tree, drop every table

Revision ID: 0066
Revises: 0065
Create Date: 2026-09-12

ADR knowledge-is-plain-files, spec knowledge FR-070/FR-071. The knowledge layer
stops being an index over files and becomes the files. Eleven tables go, and
none of them is replaced: a collection is a row in the kind-agnostic
``resources`` table like every other Resource (FR-081).

**The order is the whole point.** A document's title lives ONLY in
``documents.title`` today — the file on disk is named by a ULID and its
frontmatter never carried one. Dropping the table first would erase every title
with no way back, so ``upgrade`` runs the on-disk rewrite FIRST
(``infrastructure/knowledge/legacy_migration.py``), reading the rows it is about
to destroy, and only then drops.

What the rewrite does: ``<scope>/{notes,docs}/<ULID>.md`` becomes
``<collection>/<slug-of-title>.md`` carrying exactly ``title``,
``description``, ``actor``, ``created_at``, ``updated_at``; ``global`` lands in
``shopee`` and every ``project-<ULID>`` scope in ``coffer``; ``.raw/`` — copies
byte-identical to their lane counterparts — is deleted; the emptied scope
directories are removed; each collection gets a ``README.md`` describing it; and
the ``knowledge`` Resource rows are re-pointed from scopes to collections.

**The FTS5 drop.** ``documents_fts`` is a virtual table (created by the old
``infrastructure/knowledge/ddl.py``); dropping it removes its five shadow
tables with it. The explicit shadow drops that follow are for the one case that
does not: a database where the virtual table is already gone and its shadows
were orphaned.

Every drop is guarded so a database missing any of these still upgrades, and
the rewrite is idempotent: a re-run finds no lane directories and does nothing.

``downgrade`` raises. This is deliberately one-way — the ULID names and the
``.raw/`` copies cannot be reconstructed, and no compatibility shim is left
behind anywhere.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

from coffer.infrastructure.knowledge.legacy_migration import migrate

revision: str = "0066"
down_revision: str | None = "0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

#: The FTS5 virtual table, then the shadow tables it normally takes with it.
_FTS_TABLE = "documents_fts"
_FTS_SHADOWS = (
    "documents_fts_config",
    "documents_fts_content",
    "documents_fts_data",
    "documents_fts_docsize",
    "documents_fts_idx",
)

#: Dropped after the FTS index; ``chunks`` before ``documents`` because it is
#: the dependent side of the pair.
_DROPPED_TABLES = (
    "chunks",
    "documents",
    "embedding_config",
    "knowledge_scope_labels",
    "knowledge_scope_project_roots",
)


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def _drop_fts() -> None:
    """Drop the FTS5 virtual table, then any shadow left behind without it."""
    bind = op.get_bind()
    if _has_table(_FTS_TABLE):
        with bind.begin_nested():
            bind.execute(text(f"DROP TABLE IF EXISTS {_FTS_TABLE}"))
    for shadow in _FTS_SHADOWS:
        bind.execute(text(f"DROP TABLE IF EXISTS {shadow}"))


def upgrade() -> None:
    # 1. Read the titles out of the database and rewrite the tree around them.
    #    This MUST precede every drop below (FR-071).
    report = migrate(op.get_bind())
    logger.info("knowledge tree migrated: %s", report)

    # 2. Now the tables have nothing left to say.
    _drop_fts()
    for table in _DROPPED_TABLES:
        if _has_table(table):
            op.drop_table(table)

    # The tidy pass survives the cut, and its background worker needs somewhere
    # to be switched on. It goes on the internal-engine singleton rather than in
    # a table of its own: it governs what Coffer's own model may do unattended,
    # and FR-081 forbids the knowledge layer adding a table.
    if _has_table("internal_engine_config") and not _has_column(
        "internal_engine_config", "auto_tidy_enabled"
    ):
        op.add_column(
            "internal_engine_config",
            sa.Column(
                "auto_tidy_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


#: The tables as 0065 left them, recreated EMPTY on downgrade. The schema can
#: come back; the rows cannot — every one of them indexed a file that this
#: migration renamed, and the titles they held now live in the files themselves.
#: Recreating them is what lets the migrations below this one run their own
#: ``downgrade`` (they drop these tables and would fail on a missing one).
_RECREATE_SQL = (
    """CREATE TABLE documents (
        id VARCHAR NOT NULL, kind VARCHAR NOT NULL, resource_name VARCHAR NOT NULL,
        project_id VARCHAR NOT NULL, path VARCHAR NOT NULL, title VARCHAR NOT NULL,
        description TEXT, metadata TEXT DEFAULT '{}' NOT NULL,
        content_sha256 VARCHAR NOT NULL, source_mode VARCHAR NOT NULL,
        created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
        embed_pending BOOLEAN DEFAULT 0 NOT NULL, lane VARCHAR DEFAULT 'docs' NOT NULL,
        CONSTRAINT pk_documents PRIMARY KEY (kind, resource_name, id))""",
    "CREATE INDEX idx_documents_kind_res_lane ON documents (kind, resource_name, lane)",
    "CREATE INDEX idx_documents_kind_res_time ON documents (kind, resource_name, updated_at)",
    "CREATE INDEX idx_documents_project ON documents (project_id)",
    """CREATE TABLE chunks (
        id VARCHAR NOT NULL, document_id VARCHAR NOT NULL, kind VARCHAR NOT NULL,
        resource_name VARCHAR NOT NULL, position INTEGER NOT NULL,
        CONSTRAINT pk_chunks PRIMARY KEY (id))""",
    "CREATE INDEX idx_chunks_document ON chunks (document_id)",
    "CREATE VIRTUAL TABLE documents_fts USING fts5("
    "text, resource_name UNINDEXED, chunk_id UNINDEXED, tokenize='trigram')",
    """CREATE TABLE embedding_config (
        id INTEGER NOT NULL, enabled BOOLEAN DEFAULT 0 NOT NULL, model VARCHAR,
        dimensions INTEGER DEFAULT (768) NOT NULL, updated_at TIMESTAMP NOT NULL,
        default_chunk_size INTEGER DEFAULT (512) NOT NULL,
        default_chunk_overlap INTEGER DEFAULT (64) NOT NULL, connection VARCHAR,
        CONSTRAINT pk_embedding_config PRIMARY KEY (id),
        CONSTRAINT ck_embedding_config_singleton CHECK (id = 1))""",
    """CREATE TABLE knowledge_scope_labels (
        scope_name VARCHAR NOT NULL, label VARCHAR NOT NULL,
        PRIMARY KEY (scope_name))""",
    """CREATE TABLE knowledge_scope_project_roots (
        scope_name VARCHAR NOT NULL, project_root VARCHAR NOT NULL,
        CONSTRAINT pk_memory_store_project_roots PRIMARY KEY (scope_name))""",
)


def downgrade() -> None:
    """Put the schema back, empty, and leave the files where they are.

    This is a one-way migration in the sense that matters: the on-disk rewrite
    is not undone and the index cannot be reconstructed from it. What downgrade
    restores is the shape the migrations below expect to find, so the chain
    below this revision still runs.
    """
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for statement in _RECREATE_SQL:
        name = statement.split()[2].split("(")[0].strip('"')
        if name in existing:
            continue
        bind.execute(text(statement))
    op.drop_column("internal_engine_config", "auto_tidy_enabled")
