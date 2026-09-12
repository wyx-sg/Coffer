"""0066: the knowledge tree becomes a directory of named files.

The ordering is the point. A document's title lived ONLY in ``documents.title``
— the file on disk was named by a ULID and its frontmatter never carried one —
so this migration reads the rows it is about to destroy, writes the titles into
the tree, and only then drops the tables (spec knowledge FR-071).
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest
from alembic import command

from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

from .test_migrations_roundtrip import _alembic_config, _user_tables


def _seed_legacy_tree(root: pathlib.Path) -> None:
    """A pre-0066 vault: ULID-named files in two lanes, plus a .raw/ copy."""
    (root / "global" / "docs").mkdir(parents=True)
    (root / "global" / ".raw").mkdir(parents=True)
    (root / "project-01ABC" / "notes").mkdir(parents=True)

    (root / "global" / "docs" / "01M28PT8942MSZV75S93MGMZ9M.md").write_text(
        "---\nsource_filename: session.md\nconverter: passthrough\n---\n\n# session\n\nbody\n",
        encoding="utf-8",
    )
    (root / "global" / ".raw" / "01M28PT8942MSZV75S93MGMZ9M.md").write_text(
        "byte-identical copy", encoding="utf-8"
    )
    (root / "project-01ABC" / "notes" / "a-note-xyz.md").write_text(
        "---\ntitle: A parked idea\ndescription: d\nmetadata:\n  actor: agent\n---\n\nnote body\n",
        encoding="utf-8",
    )


def _seed_rows(db_path: pathlib.Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO documents (id, kind, resource_name, project_id, path, title, "
            "description, metadata, content_sha256, source_mode, created_at, updated_at, "
            "embed_pending, lane) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "01M28PT8942MSZV75S93MGMZ9M",
                "knowledge",
                "global",
                "global",
                "01M28PT8942MSZV75S93MGMZ9M.md",
                "session — 账号系统的登录态数据层",
                "token 签发/校验/撤销",
                "{}",
                "sha",
                "converted",
                "2026-09-11T17:04:03+00:00",
                "2026-09-11T17:04:03+00:00",
                0,
                "docs",
            ),
        )
        conn.execute(
            "INSERT INTO resources (kind, name, description, config_json, enabled, "
            "created_at, updated_at) VALUES ('knowledge','global',NULL,'{}',1,?,?)",
            ("2026-09-10T00:00:00+00:00", "2026-09-10T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="migration rewrites ULID documents into named files in collections",
)
def test_0066_names_files_from_titles_then_drops_the_tables(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "m.db"
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    cfg = _alembic_config()

    command.upgrade(cfg, "0065")
    _seed_legacy_tree(root)
    _seed_rows(db_path)

    command.upgrade(cfg, "0066")

    # The title, which existed only in the row, is now the file's name and its
    # frontmatter — the row it came from is gone.
    moved = list((root / "shopee").glob("*.md"))
    named = [p for p in moved if p.name != "README.md"]
    assert len(named) == 1
    assert "session" in named[0].name and "01M28PT" not in named[0].name
    frontmatter, _ = split_frontmatter(named[0].read_text(encoding="utf-8"))
    assert frontmatter["title"] == "session — 账号系统的登录态数据层"
    assert frontmatter["actor"] == "user"
    assert "source_filename" not in frontmatter and "converter" not in frontmatter

    # The note keeps its own title and its agent provenance.
    note = next(p for p in (root / "coffer").glob("*.md") if p.name != "README.md")
    note_frontmatter, _ = split_frontmatter(note.read_text(encoding="utf-8"))
    assert note_frontmatter["title"] == "A parked idea"
    assert note_frontmatter["actor"] == "agent"

    # The lanes, the .raw/ duplicates and the scope directories are gone.
    assert not (root / "global").exists()
    assert not (root / "project-01ABC").exists()
    assert not list(root.rglob(".raw"))

    tables = _user_tables(db_path)
    assert not ({"documents", "chunks", "documents_fts", "embedding_config"} & tables)

    # The scopes' Resource rows are replaced by one per created collection.
    conn = sqlite3.connect(db_path)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM resources WHERE kind='knowledge'")}
    finally:
        conn.close()
    assert names == {"shopee", "coffer"}


def test_0066_registers_collections_that_are_already_on_disk(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A tree already in the new shape still gets its Resource rows.

    Regression: the pass used to key the rows off what THIS run moved. A tree
    migrated by an earlier run — or restored from a backup — reports no work
    done, so the scopes' rows were deleted and nothing registered in their
    place, leaving every file on disk invisible to every agent (the per-agent
    scope reads the Resource rows, spec knowledge FR-012).
    """
    db_path = tmp_path / "m.db"
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    cfg = _alembic_config()

    command.upgrade(cfg, "0065")
    # Already migrated: collections, readable names, no lane directories.
    (root / "shopee").mkdir(parents=True)
    (root / "shopee" / "gateway.md").write_text(
        "---\ntitle: Gateway\ndescription: the orchestration layer\nactor: user\n---\n\nbody\n",
        encoding="utf-8",
    )
    _seed_rows(db_path)  # the old scope's Resource row is still there

    command.upgrade(cfg, "0066")

    conn = sqlite3.connect(db_path)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM resources WHERE kind='knowledge'")}
    finally:
        conn.close()
    assert names == {"shopee"}
    assert (root / "shopee" / "gateway.md").is_file()


def test_0066_fills_in_a_missing_description(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An empty description is not cosmetic: the catalogue is the only
    retrieval surface, so a file describing nothing is one an agent scrolls
    past (spec knowledge FR-003). Almost no pre-migration document carried one.
    """
    db_path = tmp_path / "m.db"
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    cfg = _alembic_config()

    command.upgrade(cfg, "0065")
    (root / "shopee").mkdir(parents=True)
    described = root / "shopee" / "kept.md"
    described.write_text(
        "---\ntitle: Kept\ndescription: already said\nactor: user\n---\n\nbody paragraph\n",
        encoding="utf-8",
    )
    bare = root / "shopee" / "bare.md"
    bare.write_text(
        "---\ntitle: Bare\ndescription: ''\nactor: user\n---\n\n# Heading\n\n"
        "The first real paragraph.\n\nA second one.\n",
        encoding="utf-8",
    )

    command.upgrade(cfg, "0066")

    filled, _ = split_frontmatter(bare.read_text(encoding="utf-8"))
    assert filled["description"] == "The first real paragraph."
    # A file that already describes itself is left alone.
    kept, _ = split_frontmatter(described.read_text(encoding="utf-8"))
    assert kept["description"] == "already said"
