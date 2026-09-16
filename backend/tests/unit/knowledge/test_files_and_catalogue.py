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
    # The nested file is counted but not listed: one level at a time (FR-013).
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
    """The filesystem is the ingestion surface (FR-021): no index means nothing
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
    [
        "../etc/passwd",
        "shopee/../../outside",
        ".history/old.md",
        "shopee/.history/old.md",
        ".raw/original.pdf",
        "shopee/.raw/original.pdf",
    ],
)
def test_paths_that_leave_the_root_or_name_a_hidden_entry_are_rejected(bad: str) -> None:
    with pytest.raises(UnsafeKnowledgePath):
        paths.resolve(bad)


def test_raw_path_round_trips_a_nested_file_and_keeps_the_original_extension() -> None:
    converted = paths.raw_path("shopee/account/gateway.md", "Gateway Overview.docx")
    assert converted == paths.raw_dir("shopee") / "account" / "gateway.docx"

    flat = paths.raw_path("shopee/report.md", "Q3 Report.pdf")
    assert flat == paths.raw_dir("shopee") / "report.pdf"


@pytest.mark.acceptance(
    spec="knowledge", scenario="an uploaded original is kept under .raw/ and stays out of retrieval"
)
def test_raw_dir_is_excluded_from_the_catalogue_and_its_count(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    fs.write_file(directory="shopee", title="Visible", description="d", body="b")
    raw = paths.raw_dir("shopee")
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "original.pdf").write_bytes(b"%PDF-1.4 not markdown")

    level = fs.list_level("shopee")
    assert [f.title for f in level.files] == ["Visible"]
    assert fs.list_collections()[0].file_count == 1


def test_raw_dir_is_not_addressable_through_split_or_resolve() -> None:
    with pytest.raises(UnsafeKnowledgePath):
        paths.split("shopee/.raw/original.pdf")
    with pytest.raises(UnsafeKnowledgePath):
        paths.resolve("shopee/.raw/original.pdf")


def test_readme_is_a_description_not_a_listed_file(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    paths.readme_path("shopee").write_text(
        "# shopee\n\nInternal systems.\n\nSecond paragraph.\n", encoding="utf-8"
    )
    assert fs.readme_description("shopee") == "Internal systems."
    assert fs.list_level("shopee").files == ()
    assert fs.list_collections()[0].file_count == 0


def test_a_file_may_be_all_title_and_description(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    """An empty body is legitimate — a pointer whose whole content is what it
    is and where it sits. Both write surfaces agree on this (FR-019); only the
    description is required, because that is what makes it findable (FR-003).
    """
    written = fs.write_file(
        directory="shopee", title="Pointer", description="where the real thing lives", body=""
    )
    assert written.body.strip() == ""
    assert fs.list_level("shopee").files[0].description == "where the real thing lives"


def test_a_new_file_under_a_symlinked_directory_is_refused(knowledge_root, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """FR-006: a symlink inside the root must not carry a write out of it.

    The target file does not exist yet, so the old ``exists()`` guard saw
    nothing to resolve — and the atomic write then followed the link.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (knowledge_root / "shopee" / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeKnowledgePath):
        paths.resolve("shopee/linked/new.md")
    with pytest.raises(UnsafeKnowledgePath):
        fs.write_file(directory="shopee/linked", title="Escape", description="d", body="b")
    with pytest.raises(UnsafeKnowledgePath):
        fs.write_file(
            directory="shopee",
            title="Escape",
            description="d",
            body="b",
            relpath="shopee/linked/x.md",
        )
    assert list(outside.iterdir()) == []


def test_a_dangling_symlink_pointing_outside_is_refused(knowledge_root, tmp_path) -> None:  # type: ignore[no-untyped-def]
    (knowledge_root / "shopee" / "escape.md").symlink_to(tmp_path / "outside" / "planted.md")

    with pytest.raises(UnsafeKnowledgePath):
        paths.resolve("shopee/escape.md")
    assert not (tmp_path / "outside").exists()


def test_a_symlink_that_stays_inside_the_root_is_allowed(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    (knowledge_root / "shopee" / "real").mkdir()
    (knowledge_root / "shopee" / "alias").symlink_to(
        knowledge_root / "shopee" / "real", target_is_directory=True
    )

    written = fs.write_file(directory="shopee/alias", title="Inside", description="d", body="b")

    assert (knowledge_root / "shopee" / "real" / "inside.md").is_file()
    assert written.path == "shopee/alias/inside.md"


def test_atomic_write_does_not_follow_a_planted_temp_symlink(knowledge_root, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The temp file is opened exclusively, so a link planted under its name
    is replaced rather than written through."""
    outside = tmp_path / "outside.md"
    (knowledge_root / "shopee" / ".note.md.tmp").symlink_to(outside)

    fs.write_file(directory="shopee", title="Note", description="d", body="b")

    assert not outside.exists()
    assert (knowledge_root / "shopee" / "note.md").is_file()
    assert not (knowledge_root / "shopee" / ".note.md.tmp").exists()
