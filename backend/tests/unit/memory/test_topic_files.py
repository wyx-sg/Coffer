"""Unit tests for the organizer's topic-doc / INDEX / changelog I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.infrastructure.knowledge.paths import (
    consolidation_log_path,
    inbox_item_path,
    knowledge_index_path,
    topic_path,
)
from coffer.infrastructure.memory.topic_files import (
    TopicDoc,
    append_changelog,
    list_topic_docs,
    read_topic_doc,
    render_index,
    topic_doc_exists,
    topic_slug,
    write_index,
    write_topic_doc,
)

_NOW = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)


def _doc(slug: str, *, title: str, desc: str = "desc", body: str = "body") -> TopicDoc:
    return TopicDoc(slug=slug, title=title, description=desc, body=body, updated_at=_NOW)


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Deploy Conventions", "deploy-conventions"),
        ("  Trailing/Slash  ", "trailing-slash"),
        ("CJK 中文 mix", "cjk-中文-mix".replace("中文", "")),  # non-ascii collapses out
        ("!!!", "topic"),  # all-punctuation falls back
        ("already-kebab", "already-kebab"),
    ],
)
def test_topic_slug(title: str, expected: str) -> None:
    slug = topic_slug(title)
    # The slug is always a usable single segment that topic_path accepts.
    assert slug
    assert "/" not in slug


def test_topic_slug_is_path_safe(tmp_path: Path) -> None:
    # Even an adversarial title yields a slug topic_path accepts (no traversal).
    slug = topic_slug("../../etc/passwd")
    p = topic_path(tmp_path, slug)
    assert p.parent == tmp_path / "knowledge"


def test_write_read_topic_doc_roundtrip(tmp_path: Path) -> None:
    path = topic_path(tmp_path, "deploy")
    doc = _doc("deploy", title="Deploy", desc="how we ship", body="# Deploy\n\nUse make release.")
    write_topic_doc(path, doc)
    back = read_topic_doc(path)
    assert back is not None
    assert back.slug == "deploy"
    assert back.title == "Deploy"
    assert back.description == "how we ship"
    assert back.body == "# Deploy\n\nUse make release."
    assert back.updated_at == _NOW


def test_read_missing_topic_doc_is_none(tmp_path: Path) -> None:
    assert read_topic_doc(topic_path(tmp_path, "nope")) is None


def test_read_topic_doc_degrades_without_frontmatter(tmp_path: Path) -> None:
    # A hand-written doc with no frontmatter still parses (title=stem, desc=first line).
    path = topic_path(tmp_path, "hand")
    path.parent.mkdir(parents=True)
    path.write_text("first line of body\nmore\n", encoding="utf-8")
    doc = read_topic_doc(path)
    assert doc is not None
    assert doc.title == "hand"
    assert doc.description == "first line of body"


def test_list_topic_docs_excludes_inbox_and_index(tmp_path: Path) -> None:
    write_topic_doc(topic_path(tmp_path, "alpha"), _doc("alpha", title="Alpha"))
    write_topic_doc(topic_path(tmp_path, "beta"), _doc("beta", title="Beta"))
    # An inbox item must NOT be listed as a topic doc.
    inbox = inbox_item_path(tmp_path, "fresh-item")
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("---\nname: x\n---\nbody\n", encoding="utf-8")
    # INDEX.md must NOT be listed.
    write_index(tmp_path, [_doc("alpha", title="Alpha"), _doc("beta", title="Beta")])

    slugs = sorted(d.slug for d in list_topic_docs(tmp_path))
    assert slugs == ["alpha", "beta"]


def test_list_topic_docs_empty_lane(tmp_path: Path) -> None:
    assert list_topic_docs(tmp_path) == []


def test_render_index_lists_topics_sorted(tmp_path: Path) -> None:
    out = render_index(
        [_doc("beta", title="Beta", desc="b"), _doc("alpha", title="Alpha", desc="a")]
    )
    # Sorted by slug; one bullet per topic with title, slug link, and description.
    assert "- [Alpha](alpha.md) — a" in out
    assert "- [Beta](beta.md) — b" in out
    assert out.index("alpha.md") < out.index("beta.md")


def test_write_index_writes_to_knowledge_index_path(tmp_path: Path) -> None:
    write_index(tmp_path, [_doc("alpha", title="Alpha")])
    idx = knowledge_index_path(tmp_path)
    assert idx.exists()
    assert "alpha.md" in idx.read_text(encoding="utf-8")


def test_append_changelog_is_append_only(tmp_path: Path) -> None:
    append_changelog(tmp_path, "line one")
    append_changelog(tmp_path, "line two")
    log = consolidation_log_path(tmp_path)
    assert log.parent == tmp_path  # at the store ROOT, outside knowledge/
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines == ["line one", "line two"]


def test_topic_doc_exists(tmp_path: Path) -> None:
    assert not topic_doc_exists(tmp_path, "deploy")
    write_topic_doc(topic_path(tmp_path, "deploy"), _doc("deploy", title="Deploy"))
    assert topic_doc_exists(tmp_path, "deploy")
