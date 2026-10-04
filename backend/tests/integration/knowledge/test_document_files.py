"""Document files on disk: what a rewrite keeps, what is listed, what is oldest.

Real filesystem under the test's own knowledge root (the conftest points
``COFFER_KNOWLEDGE_ROOT`` at a temp directory).
"""

from __future__ import annotations

import os

import pytest

from coffer.infrastructure.knowledge import catalogue, fs, inbox, paths
from coffer.infrastructure.knowledge.paths import knowledge_root


@pytest.fixture(autouse=True)
def _collection() -> None:
    knowledge_root()
    fs.create_collection_dir("shopee")


def test_a_rewrite_keeps_the_keys_a_person_added() -> None:
    created = fs.write_file(directory="shopee", title="Login", description="d", body="v1")
    target = paths.resolve(created.path)
    target.write_text(
        target.read_text().replace(
            "---\n\n", "tags:\n- auth\nreviewed_by: yuxing\ndraft: false\nlevel: 0\n---\n\n", 1
        )
    )

    fs.write_file(
        directory="shopee",
        title="Login",
        description="d2",
        body="v2",
        relpath=created.path,
    )

    text = target.read_text()
    assert "description: d2" in text
    assert "reviewed_by: yuxing" in text
    assert "- auth" in text
    # Falsy values are values: dropping `draft: false` would change what it says.
    assert "draft: false" in text
    assert "level: 0" in text
    assert fs.read_file(created.path).created_at == created.created_at


def test_a_nested_readme_is_a_document_and_only_the_collection_readme_is_not() -> None:
    (paths.collection_dir("shopee") / "README.md").write_text("# shopee\n\nAbout.\n")
    (paths.collection_dir("shopee") / "guide").mkdir()
    (paths.collection_dir("shopee") / "guide" / "README.md").write_text(
        "# Guide\n\nA nested one.\n"
    )
    fs.write_file(directory="shopee", title="Real", description="d", body="b")

    walked = [f.path for f in catalogue.walk_files(paths.collection_dir("shopee"))]
    listed = [f.path for f in catalogue.list_level("shopee").files]

    assert walked == ["shopee/guide/README.md", "shopee/real.md"]
    assert listed == ["shopee/real.md"]
    assert catalogue.count_files(paths.collection_dir("shopee"), markdown_only=True) == 2
    paths.require_document("shopee/guide/README.md")
    with pytest.raises(Exception, match="README"):
        paths.require_document("shopee/README.md")


def test_inbox_items_are_ordered_by_when_they_were_submitted_not_by_file_time() -> None:
    first = inbox.submit_material("shopee", title="First", description="d", body="a", actor="user")
    second = inbox.submit_material(
        "shopee", title="Second", description="d", body="b", actor="user"
    )
    # A checkout or a sync round rewrites file times and reverses them.
    base = paths.inbox_dir("shopee")
    os.utime(base / first, (2_000_000_000, 2_000_000_000))
    os.utime(base / second, (1_000_000_000, 1_000_000_000))
    # Same-second submissions: pin created_at explicitly.
    (base / first).write_text(
        (base / first)
        .read_text()
        .replace(_created(base / first), "created_at: '2026-01-01T00:00:00+00:00'")
    )
    (base / second).write_text(
        (base / second)
        .read_text()
        .replace(_created(base / second), "created_at: '2026-02-01T00:00:00+00:00'")
    )

    assert inbox.inbox_items("shopee") == (first, second)


def _created(path) -> str:  # type: ignore[no-untyped-def]
    return next(line for line in path.read_text().splitlines() if line.startswith("created_at:"))
