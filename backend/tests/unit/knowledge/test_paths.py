"""Unit tests for substrate path construction + traversal guards."""

import pytest

from coffer.infrastructure.knowledge import paths


def test_knowledge_root_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    assert paths.knowledge_root() == tmp_path / "k"
    assert paths.docs_dir("kb1") == tmp_path / "k" / "kb1" / "inbox"
    assert paths.raw_dir("kb1") == tmp_path / "k" / "kb1" / ".raw"


def test_doc_and_raw_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    assert paths.doc_path("kb1", "abcd1234").name == "abcd1234.md"
    assert paths.raw_path("kb1", "abcd1234", "pdf").name == "abcd1234.pdf"
    assert paths.raw_path("kb1", "abcd1234", ".pdf").name == "abcd1234.pdf"


def test_scope_name_traversal_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    for bad in ["..", "../evil", "a/b", "."]:
        with pytest.raises(ValueError):
            paths.scope_dir(bad)


def test_every_scope_lives_under_the_one_root(monkeypatch, tmp_path) -> None:
    """global, a project scope, and a named collection are all siblings."""
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    root = tmp_path / "k"
    assert paths.scope_dir("global") == root / "global"
    pid = "01ABCDEF0123456789ABCDEFGH"
    assert paths.scope_dir(f"project-{pid}") == root / f"project-{pid}"
    assert paths.scope_dir("team-notes") == root / "team-notes"


def test_fact_path_guard(monkeypatch, tmp_path) -> None:
    store = tmp_path / "store"
    assert paths.fact_path(store, "my-fact").name == "my-fact.md"
    with pytest.raises(ValueError):
        paths.fact_path(store, "../evil")


def test_knowledge_lane_paths(monkeypatch, tmp_path) -> None:
    store = tmp_path / "store"
    assert paths.knowledge_dir(store) == store / "knowledge"
    assert paths.inbox_dir(store) == store / "knowledge" / "inbox"
    item = paths.inbox_item_path(store, "deploy-01abcdef")
    assert item == store / "knowledge" / "inbox" / "deploy-01abcdef.md"
    assert item.name == "deploy-01abcdef.md"


def test_inbox_item_path_rejects_traversal(monkeypatch, tmp_path) -> None:
    store = tmp_path / "store"
    with pytest.raises(ValueError):
        paths.inbox_item_path(store, "../evil")


def test_raw_path_rejects_slashed_ext(monkeypatch, tmp_path) -> None:
    """A slash-containing ext (from an upload filename) must not create nested
    subdirs inside raw/; it is rejected as an unsafe segment."""
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    for bad_ext in ["a/b", "../evil", "sub/dir.pdf", "/etc", ".d/../x"]:
        with pytest.raises(ValueError):
            paths.raw_path("kb1", "abcd1234", bad_ext)


def test_doc_and_fact_path_reject_slashed_segment(monkeypatch, tmp_path) -> None:
    """doc_id / slug confined to a single path segment (defense-in-depth)."""
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "k"))
    store = tmp_path / "store"
    for bad_id in ["a/b", "../evil"]:
        with pytest.raises(ValueError):
            paths.doc_path("kb1", bad_id)
        with pytest.raises(ValueError):
            paths.raw_path("kb1", bad_id, "pdf")
        with pytest.raises(ValueError):
            paths.fact_path(store, bad_id)
