"""The knowledge layer is a directory, so these are filesystem tests.

Nothing here goes through a service or a route: the substrate is
``infrastructure/knowledge``, and if the two lanes and the walk over them are
right, every surface above is reading the truth (spec knowledge FR-001).

What these pin that the old single-lane tests could not: a write lands in the
lane its caller named and nowhere else, and the watermark that decides what
curation still owes is read off the file rather than out of any state Coffer
keeps (FR-028).
"""

from __future__ import annotations

import pathlib
import time

import pytest

from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.infrastructure.knowledge import catalogue, fs, paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter


@pytest.fixture(autouse=True)
def knowledge_root(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    fs.create_collection_dir("shopee")
    return root


def _source(title: str = "Session", body: str = "body") -> str:
    return fs.write_file(
        directory="shopee/sources", title=title, description="d", body=body, actor="user"
    ).path


# ----- lanes ---------------------------------------------------------------


def test_creating_a_collection_creates_both_lanes(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    assert (knowledge_root / "shopee" / "sources").is_dir()
    assert (knowledge_root / "shopee" / "topics").is_dir()


@pytest.mark.acceptance(spec="knowledge", scenario="a written note lands in the sources lane")
def test_a_write_lands_in_the_named_lane(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source(title="Account Gateway")
    assert relpath == "shopee/sources/account-gateway.md"
    # The file name is the title's own slug and carries no id anywhere.
    assert "account-gateway" in relpath and "01" not in pathlib.Path(relpath).stem
    # Nothing reached the curated lane.
    assert catalogue.count_files(paths.topics_dir("shopee")) == 0


@pytest.mark.acceptance(
    spec="knowledge", scenario="frontmatter carries title, description and actor"
)
def test_frontmatter_carries_the_five_fields(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    written = fs.write_file(
        directory="shopee/sources",
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


def test_a_write_outside_a_lane_is_refused(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # The collection root belongs to README.md and the two lanes; a content
    # file there would be in neither, so nothing could say who may rewrite it.
    with pytest.raises(UnsafeKnowledgePath):
        fs.write_file(directory="shopee", title="Stray", description="d", body="b")


def test_require_lane_pins_which_lane(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source()
    assert paths.require_lane(relpath, expected="sources") == "sources"
    with pytest.raises(UnsafeKnowledgePath):
        paths.require_lane(relpath, expected="topics")


@pytest.mark.acceptance(spec="knowledge", scenario="a path escaping the knowledge root is rejected")
@pytest.mark.parametrize(
    "bad",
    ["../etc/passwd", "shopee/../../outside", ".history/old.md", "shopee/.raw/original.pdf"],
)
def test_traversal_and_hidden_entries_are_refused(bad: str) -> None:
    with pytest.raises(UnsafeKnowledgePath):
        paths.resolve(bad)


def test_collections_count_the_lanes_apart(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    _source(title="One")
    fs.write_file(directory="shopee/topics", title="Two", description="d", body="b")
    fs.write_file(directory="shopee/topics", title="Three", description="d", body="b")
    entry = next(c for c in catalogue.list_collections() if c.name == "shopee")
    assert (entry.source_count, entry.topic_count) == (1, 2)


def test_readme_stays_out_of_both_lanes_and_out_of_the_counts(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    paths.readme_path("shopee").write_text("# shopee\n\nInternal systems.\n", encoding="utf-8")
    entry = next(c for c in catalogue.list_collections() if c.name == "shopee")
    assert entry.description == "Internal systems."
    assert (entry.source_count, entry.topic_count) == (0, 0)


def test_walk_files_returns_a_whole_lane_recursively(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    fs.write_file(directory="shopee/topics", title="Top", description="d", body="b")
    fs.write_file(directory="shopee/topics/account", title="Nested", description="d", body="b")
    found = catalogue.walk_files(paths.topics_dir("shopee"))
    assert [f.path for f in found] == [
        "shopee/topics/account/nested.md",
        "shopee/topics/top.md",
    ]


# ----- the watermark -------------------------------------------------------


def test_a_new_source_is_pending(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source()
    assert fs.pending_sources("shopee") == (relpath,)


@pytest.mark.acceptance(spec="knowledge", scenario="a source is curated once, not on every sweep")
def test_a_stamped_source_stops_being_pending_until_it_changes(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source()
    fs.mark_ingested(relpath)
    assert fs.pending_sources("shopee") == ()

    # The stamp is on the file, and it is the file's own modification time it
    # is compared against — so touching the file makes it owed again with
    # nothing else consulted.
    time.sleep(0.01)
    path = paths.resolve(relpath)
    path.write_text(path.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    assert fs.pending_sources("shopee") == (relpath,)


def test_marking_changes_nothing_but_the_stamp(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _source(body="the original body")
    before = fs.read_file(relpath)
    fs.mark_ingested(relpath, when="2026-09-17T00:00:00+00:00")
    after = fs.read_file(relpath)
    assert after.body == before.body
    assert (after.title, after.description, after.actor) == (
        before.title,
        before.description,
        before.actor,
    )
    assert after.created_at == before.created_at
    assert after.ingested_at == "2026-09-17T00:00:00+00:00"


def test_stamping_keeps_frontmatter_coffer_did_not_write(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # `sources/` is the lane this design promises belongs to the person, and
    # the stamp is Coffer editing a file it did not author, unattended, on a
    # timer. Dropping a key it does not recognise would delete their own
    # `tags:` from under them.
    relpath = _source()
    path = paths.resolve(relpath)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "actor: user", "actor: user\ntags: [account, session]\nreviewed_by: yuxing"
        ),
        encoding="utf-8",
    )
    fs.mark_ingested(relpath)
    frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    assert frontmatter["tags"] == ["account", "session"]
    assert frontmatter["reviewed_by"] == "yuxing"
    assert frontmatter[fs.INGESTED_AT_KEY]


def test_a_replaced_source_loses_its_stamp(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # New bytes are material curation has not seen, so a replace must put the
    # file back in the queue rather than inherit a stamp that predates it.
    relpath = _source()
    fs.mark_ingested(relpath)
    fs.write_file(relpath=relpath, directory="", title="Session", description="d", body="new")
    assert fs.read_file(relpath).ingested_at == ""
    assert fs.pending_sources("shopee") == (relpath,)


def test_only_a_source_may_be_stamped(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    topic = fs.write_file(directory="shopee/topics", title="T", description="d", body="b")
    with pytest.raises(UnsafeKnowledgePath):
        fs.mark_ingested(topic.path)


# ----- uploaded originals --------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload lands both the original and its text in sources"
)
def test_an_original_is_an_ordinary_visible_file(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = fs.write_original("shopee", "Runbook.txt", b"raw bytes")
    assert relpath == "shopee/sources/runbook.txt"
    assert paths.resolve(relpath).read_bytes() == b"raw bytes"
    # No hidden directory is created for it — the whole reason `.raw/` existed
    # was to keep an original out of a retrieval surface that no longer exists.
    assert not any(p.name.startswith(".") for p in (knowledge_root / "shopee").iterdir())


def test_an_original_is_visible_in_the_lane_a_person_browses(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # It is not enough that the bytes are on disk: a lane that shows the
    # extracted text but hides the PDF the person actually sent is lying about
    # its own contents, and the original would then be reachable only through
    # the upload response that created it (FR-016, FR-040).
    fs.write_file(
        directory="shopee/sources", title="Runbook", description="d", body="b", actor="user"
    )
    fs.write_original("shopee", "Runbook.txt", b"raw bytes")
    listed = {f.path: f for f in catalogue.list_level("shopee/sources").files}
    assert set(listed) == {"shopee/sources/runbook.md", "shopee/sources/runbook.txt"}
    # Described by its own name, not opened: it is bytes, not prose.
    assert listed["shopee/sources/runbook.txt"].title == "runbook.txt"
    assert listed["shopee/sources/runbook.txt"].description == ""

    entry = next(c for c in catalogue.list_collections() if c.name == "shopee")
    assert entry.source_count == 2

    # But the narrow rule still governs what curation and the catalogue see:
    # neither can do anything with a PDF.
    assert [f.path for f in catalogue.walk_files(paths.sources_dir("shopee"))] == [
        "shopee/sources/runbook.md"
    ]
    assert fs.pending_sources("shopee") == ("shopee/sources/runbook.md",)


def test_a_second_original_of_the_same_name_does_not_overwrite(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    first = fs.write_original("shopee", "runbook.txt", b"one")
    second = fs.write_original("shopee", "runbook.txt", b"two")
    assert first != second
    assert paths.resolve(first).read_bytes() == b"one"
    assert paths.resolve(second).read_bytes() == b"two"
