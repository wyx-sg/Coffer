"""Unit: KB ``pipeline_helpers`` pure functions."""

from __future__ import annotations

from coffer.application.knowledge_base.pipeline_helpers import document_from_frontmatter


def test_document_from_frontmatter_omits_absent_source_path() -> None:
    """Reindex-from-frontmatter rebuild: a byte-upload doc (no ``source_path`` in
    its frontmatter) must NOT gain a phantom ``source_path`` key — a stored
    ``None`` would surface as a bogus "missing" source on the next
    ``check_sources``. A present path is preserved."""
    without = document_from_frontmatter("kb1", "d1", {"title": "T", "source_filename": "a.md"})
    assert "source_path" not in without.metadata

    with_path = document_from_frontmatter(
        "kb1", "d2", {"title": "T", "source_filename": "a.md", "source_path": "/abs/a.md"}
    )
    assert with_path.metadata["source_path"] == "/abs/a.md"
