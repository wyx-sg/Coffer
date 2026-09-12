"""The knowledge layer is a directory, so these are filesystem tests.

Nothing here goes through a service or a route: the substrate is
``infrastructure/knowledge``, and if the files and the walk over them are right
every surface above is reading the truth (spec knowledge FR-001).
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.infrastructure.knowledge import fs, paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter


@pytest.fixture(autouse=True)
def knowledge_root(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    fs.create_collection_dir("shopee")
    return root


@pytest.mark.acceptance(
    spec="knowledge", scenario="frontmatter carries title, description and actor"
)
def test_frontmatter_carries_the_five_fields(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    written = fs.write_file(
        directory="shopee",
        title="Account Gateway",
        description="Where account decisions are made",
        body="body",
        actor="user",
    )
    raw = pathlib.Path(written.file_path).read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(raw)
    assert set(frontmatter) == {"title", "description", "actor", "created_at", "updated_at"}
    assert frontmatter["title"] == "Account Gateway"
    assert frontmatter["actor"] == "user"
    assert body.strip() == "body"


@pytest.mark.acceptance(
    spec="knowledge", scenario="write creates a file and replaces an existing one"
)
def test_write_replaces_in_place_and_keeps_created_at(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    first = fs.write_file(directory="shopee", title="Session", description="d", body="first")
    second = fs.write_file(
        relpath=first.path, directory="", title="Session", description="d2", body="second"
    )
    assert second.path == first.path
    assert second.body.strip() == "second"
    # The file is its own history: a replace must not look newly created.
    assert second.created_at == first.created_at
    assert len(fs.list_level("shopee").files) == 1


@pytest.mark.acceptance(spec="knowledge", scenario="the catalogue lists one level of a collection")
def test_catalogue_lists_one_level_only(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    fs.write_file(directory="shopee", title="Top", description="t", body="b")
    fs.write_file(directory="shopee/account", title="Nested", description="n", body="b")

    level = fs.list_level("shopee")
    assert [f.title for f in level.files] == ["Top"]
    assert [d.name for d in level.directories] == ["account"]
    # The nested file is counted but not listed: one level at a time (FR-021).
    assert level.directories[0].file_count == 1


@pytest.mark.acceptance(spec="knowledge", scenario="the catalogue walks into a nested directory")
def test_catalogue_walks_into_a_nested_directory(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    fs.write_file(directory="shopee/account/core", title="Deep", description="d", body="b")
    level = fs.list_level("shopee/account/core")
    assert [f.title for f in level.files] == ["Deep"]
    assert level.path == "shopee/account/core"


@pytest.mark.acceptance(
    spec="knowledge", scenario="a file added out-of-band is visible to the next call"
)
def test_a_hand_placed_file_needs_no_import(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    """The filesystem is the ingestion surface (FR-032): no index means nothing
    to reconcile, so a file dropped in by hand is simply there."""
    dropped = knowledge_root / "shopee" / "dropped-by-hand.md"
    dropped.write_text(
        "---\ntitle: Dropped\ndescription: put here from Finder\n---\n\nbody\n",
        encoding="utf-8",
    )
    level = fs.list_level("shopee")
    assert [f.title for f in level.files] == ["Dropped"]
    assert fs.read_file("shopee/dropped-by-hand.md").body.strip() == "body"


@pytest.mark.acceptance(spec="knowledge", scenario="a path escaping the knowledge root is rejected")
@pytest.mark.parametrize(
    "bad",
    ["../etc/passwd", "shopee/../../outside", ".history/old.md", "shopee/.history/old.md"],
)
def test_paths_that_leave_the_root_or_name_a_hidden_entry_are_rejected(bad: str) -> None:
    with pytest.raises(UnsafeKnowledgePath):
        paths.resolve(bad)


def test_readme_is_a_description_not_a_listed_file(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    paths.readme_path("shopee").write_text(
        "# shopee\n\nInternal systems.\n\nSecond paragraph.\n", encoding="utf-8"
    )
    assert fs.readme_description("shopee") == "Internal systems."
    assert fs.list_level("shopee").files == ()
    assert fs.list_collections()[0].file_count == 0


def test_a_file_may_be_all_title_and_description(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    """An empty body is legitimate — a pointer whose whole content is what it
    is and where it sits. Both write surfaces agree on this (FR-030); only the
    description is required, because that is what makes it findable (FR-003).
    """
    written = fs.write_file(
        directory="shopee", title="Pointer", description="where the real thing lives", body=""
    )
    assert written.body.strip() == ""
    assert fs.list_level("shopee").files[0].description == "where the real thing lives"
