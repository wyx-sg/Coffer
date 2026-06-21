"""Unit: KB ``pipeline_helpers`` pure functions."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.knowledge_base.pipeline_helpers import (
    Prepared,
    document_from_frontmatter,
    render_ingest_markdown,
)
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

_MTIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_document_from_frontmatter_omits_absent_source_path() -> None:
    """Reindex-from-frontmatter rebuild: a byte-upload doc (no ``source_path`` in
    its frontmatter) must NOT gain a phantom ``source_path`` key — a stored
    ``None`` would surface as a bogus "missing" source on the next
    ``check_sources``. A present path is preserved."""
    without = document_from_frontmatter(
        "kb1", "d1", {"title": "T", "source_filename": "a.md"}, mtime=_MTIME
    )
    assert "source_path" not in without.metadata

    with_path = document_from_frontmatter(
        "kb1",
        "d2",
        {"title": "T", "source_filename": "a.md", "source_path": "/abs/a.md"},
        mtime=_MTIME,
    )
    assert with_path.metadata["source_path"] == "/abs/a.md"


def test_ingest_frontmatter_round_trips_timestamps() -> None:
    """KB18: an ingest writes ``created_at``/``updated_at`` into the on-disk
    frontmatter, and a rebuild reads the FILE's values back — NOT now()/mtime —
    so a DB-loss rebuild restores the real ingest/edit time (files are truth)."""
    prepared = Prepared(
        doc_id="d1",
        source_sha256="sha",
        extension=".md",
        markdown="# Title\n\nbody",
        title="Title",
        conversion_engine="markitdown",
    )
    created = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    updated = datetime(2025, 6, 2, 12, 0, 0, tzinfo=UTC)
    text = render_ingest_markdown(prepared, "a.md", created_at=created, updated_at=updated)

    fm, _ = split_frontmatter(text)
    assert fm["created_at"] == created.isoformat()
    assert fm["updated_at"] == updated.isoformat()

    # Rebuild from that frontmatter with an UNRELATED mtime → the file's recorded
    # timestamps win over the mtime fallback.
    rebuilt = document_from_frontmatter("kb1", "d1", fm, mtime=_MTIME)
    assert rebuilt.created_at == created
    assert rebuilt.updated_at == updated
    assert rebuilt.created_at != _MTIME


def test_document_from_frontmatter_falls_back_to_mtime() -> None:
    """A pre-existing / hand-written file lacking the timestamp keys falls back
    to the passed file ``mtime`` (NOT now()) — back-compatible, no migration."""
    rebuilt = document_from_frontmatter(
        "kb1", "d1", {"title": "T", "source_filename": "a.md"}, mtime=_MTIME
    )
    assert rebuilt.created_at == _MTIME
    assert rebuilt.updated_at == _MTIME


def test_document_from_frontmatter_blank_timestamps_fall_back() -> None:
    """A blank / unparseable timestamp string also degrades to the mtime."""
    rebuilt = document_from_frontmatter(
        "kb1",
        "d1",
        {"title": "T", "source_filename": "a.md", "created_at": "", "updated_at": "not-a-date"},
        mtime=_MTIME,
    )
    assert rebuilt.created_at == _MTIME
    assert rebuilt.updated_at == _MTIME
