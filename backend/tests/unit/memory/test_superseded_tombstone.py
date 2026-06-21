"""Unit tests for superseded-tombstone primitives (data-loss guard for the reorg pass).

TDD: written BEFORE the implementation; expected to be RED on first run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.infrastructure.knowledge.paths import (
    knowledge_dir,
    superseded_dir,
    superseded_path,
    topic_path,
)
from coffer.infrastructure.memory.topic_files import (
    TopicDoc,
    archive_topic_doc,
    supersede_topic_doc,
    write_topic_doc,
)

_DT = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)
_SLUG = "deploy"


def _make_topic(store: Path, slug: str = _SLUG, body: str = "X: run make release") -> Path:
    doc = TopicDoc(
        slug=slug,
        title="Deploy",
        description="d",
        body=body,
        updated_at=_DT,
    )
    p = topic_path(store, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_topic_doc(p, doc)
    return p


# ---------------------------------------------------------------------------
# 1. superseded_dir is a store-ROOT sibling of knowledge/
# ---------------------------------------------------------------------------


def test_superseded_dir_is_store_root_sibling(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    sd = superseded_dir(store)
    assert sd == store / "superseded"
    assert not sd.is_relative_to(knowledge_dir(store))


# ---------------------------------------------------------------------------
# 2. superseded_path guards against traversal
# ---------------------------------------------------------------------------


def test_superseded_path_valid(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    p = superseded_path(store, "deploy-20260621T120000")
    assert p.is_relative_to(superseded_dir(store))
    assert p.name == "deploy-20260621T120000.md"


def test_superseded_path_traversal_raises(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    with pytest.raises(ValueError):
        superseded_path(store, "../escape")


# ---------------------------------------------------------------------------
# 3. archive_topic_doc copies, preserves original
# ---------------------------------------------------------------------------


def test_archive_copies_and_preserves_original(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    orig_path = _make_topic(store)
    orig_bytes = orig_path.read_bytes()

    archive = archive_topic_doc(store, _SLUG, when=_DT)

    assert archive is not None
    assert archive.is_relative_to(superseded_dir(store))
    assert archive.read_bytes() == orig_bytes
    # Original must still exist unchanged
    assert orig_path.exists()
    assert orig_path.read_bytes() == orig_bytes


def test_archive_missing_slug_returns_none(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    # No topic written
    result = archive_topic_doc(store, "nonexistent", when=_DT)
    assert result is None


# ---------------------------------------------------------------------------
# 4. archive captures a human edit (reads current disk bytes)
# ---------------------------------------------------------------------------


def test_archive_captures_human_edit(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    orig_path = _make_topic(store)
    # Simulate a human edit directly on disk
    edited_bytes = b"# manually edited\n\nsome human content\n"
    orig_path.write_bytes(edited_bytes)

    archive = archive_topic_doc(store, _SLUG, when=_DT)

    assert archive is not None
    assert archive.read_bytes() == edited_bytes


# ---------------------------------------------------------------------------
# 5. supersede_topic_doc archives THEN removes
# ---------------------------------------------------------------------------


def test_supersede_archives_then_removes(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    orig_path = _make_topic(store)
    prior_bytes = orig_path.read_bytes()

    archive = supersede_topic_doc(store, _SLUG, when=_DT)

    assert archive is not None
    # Original must be gone
    assert not orig_path.exists()
    # Archive must hold the prior content
    assert archive.is_relative_to(superseded_dir(store))
    assert archive.read_bytes() == prior_bytes


def test_supersede_missing_slug_returns_none(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    result = supersede_topic_doc(store, "nonexistent", when=_DT)
    assert result is None


# ---------------------------------------------------------------------------
# 6. collision — two archives at the same timestamp get distinct filenames
# ---------------------------------------------------------------------------


def test_archive_collision_produces_distinct_files(tmp_path: Path) -> None:
    store = tmp_path / "store"
    store.mkdir()

    # First archive
    _make_topic(store, body="first body")
    archive1 = archive_topic_doc(store, _SLUG, when=_DT)
    assert archive1 is not None

    # Re-create the topic (so a second archive has something to read)
    _make_topic(store, body="second body")
    archive2 = archive_topic_doc(store, _SLUG, when=_DT)
    assert archive2 is not None

    # Must be distinct paths
    assert archive1 != archive2
    # Both must exist
    assert archive1.exists()
    assert archive2.exists()
