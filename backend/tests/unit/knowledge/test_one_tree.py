"""The knowledge layer is a directory, so these are filesystem tests.

Nothing here goes through a service or a route: the substrate is
``infrastructure/knowledge``, and if the one tree, the inbox and the walk over
them are right, every surface above is reading the truth (spec knowledge
FR-001).

What these pin: a collection is one tree of documents with a README beside
them, new material waits in a hidden inbox that nothing lists, and the stamp
that decides which documents curation still owes is read off the file rather
than out of any state Coffer keeps (FR-028).
"""

from __future__ import annotations

import pathlib
import time

import pytest

from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.infrastructure.knowledge import catalogue, fs, paths
from coffer.infrastructure.knowledge.frontmatter import render_frontmatter, split_frontmatter


@pytest.fixture(autouse=True)
def knowledge_root(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    fs.create_collection_dir("shopee")
    return root


def _document(title: str = "Session", body: str = "body", *, curated: bool = False) -> str:
    return fs.write_file(
        directory="shopee", title=title, description="d", body=body, actor="user", curated=curated
    ).path


# ----- the tree ------------------------------------------------------------


def test_creating_a_collection_creates_one_directory(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    assert (knowledge_root / "shopee").is_dir()
    assert list((knowledge_root / "shopee").iterdir()) == []


def test_a_document_lands_in_the_collection_under_its_title(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _document(title="Account Gateway")
    assert relpath == "shopee/account-gateway.md"
    # The file name is the title's own slug and carries no id anywhere.
    assert "01" not in pathlib.Path(relpath).stem


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


@pytest.mark.parametrize("bad", ["shopee", "shopee/README.md"])
def test_a_path_that_is_not_a_document_is_refused(bad: str) -> None:
    # The collection itself and its README describe the collection; neither is
    # knowledge in it, so neither may be written, deleted or stamped as one.
    with pytest.raises(UnsafeKnowledgePath):
        paths.require_document(bad)


@pytest.mark.acceptance(spec="knowledge", scenario="a path escaping the knowledge root is rejected")
@pytest.mark.parametrize(
    "bad",
    ["../etc/passwd", "shopee/../../outside", ".history/old.md", "shopee/.inbox/material.md"],
)
def test_traversal_and_hidden_entries_are_refused(bad: str) -> None:
    with pytest.raises(UnsafeKnowledgePath):
        paths.resolve(bad)


def test_collections_count_documents_and_pending_material_apart(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    _document(title="One")
    _document(title="Two")
    fs.submit_material("shopee", title="Waiting", description="d", body="b")
    entry = next(c for c in catalogue.list_collections() if c.name == "shopee")
    assert (entry.document_count, entry.pending_count) == (2, 1)


def test_readme_stays_out_of_the_documents_and_the_counts(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    paths.readme_path("shopee").write_text("# shopee\n\nInternal systems.\n", encoding="utf-8")
    entry = next(c for c in catalogue.list_collections() if c.name == "shopee")
    assert entry.description == "Internal systems."
    assert (entry.document_count, entry.pending_count) == (0, 0)
    assert catalogue.walk_files(paths.collection_dir("shopee")) == ()


def test_walk_files_returns_the_whole_tree_and_never_the_inbox(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    fs.write_file(directory="shopee", title="Top", description="d", body="b")
    fs.write_file(directory="shopee/account", title="Nested", description="d", body="b")
    fs.submit_material("shopee", title="Waiting", description="d", body="b")
    found = catalogue.walk_files(paths.collection_dir("shopee"))
    assert [f.path for f in found] == ["shopee/account/nested.md", "shopee/top.md"]
    # A person browsing the collection does not see the inbox either.
    level = catalogue.list_level("shopee")
    assert [d.name for d in level.directories] == ["account"]
    assert [f.path for f in level.files] == ["shopee/top.md"]


# ----- the inbox -----------------------------------------------------------


def test_material_waits_in_a_hidden_inbox(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    name = fs.submit_material("shopee", title="Gateway", description="d", body="b")
    assert name == "gateway.md"
    assert (knowledge_root / "shopee" / ".inbox" / "gateway.md").is_file()
    # Two submissions of one title are two pieces of material.
    assert fs.submit_material("shopee", title="Gateway", description="d", body="c") != name
    assert len(fs.inbox_items("shopee")) == 2


def test_promoting_material_makes_it_a_stamped_document(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    name = fs.submit_material("shopee", title="Gateway", description="what it does", body="b")
    promoted = fs.promote("shopee", name)
    assert promoted.path == "shopee/gateway.md"
    assert (promoted.title, promoted.description, promoted.body.strip()) == (
        "Gateway",
        "what it does",
        "b",
    )
    assert promoted.curated_at != ""
    assert fs.inbox_items("shopee") == ()
    assert fs.edited_documents("shopee") == ()


@pytest.mark.parametrize("bad", ["../x.md", ".hidden.md", "a/b.md"])
def test_an_inbox_item_is_named_by_its_file_name_alone(bad: str) -> None:
    with pytest.raises(UnsafeKnowledgePath):
        fs.read_material("shopee", bad)


# ----- the curation stamp ---------------------------------------------------


def test_a_document_nobody_curated_is_owed(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # A person writing a document from scratch in their editor is an edit like
    # any other: the sweep picks it up.
    relpath = _document()
    assert fs.edited_documents("shopee") == (relpath,)


@pytest.mark.acceptance(spec="knowledge", scenario="an item is curated once, not on every sweep")
def test_a_stamped_document_stops_being_owed_until_it_changes(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _document()
    fs.mark_curated(relpath)
    assert fs.edited_documents("shopee") == ()

    # The stamp is on the file, and it is the file's own modification time it
    # is compared against — so touching the file makes it owed again with
    # nothing else consulted.
    time.sleep(0.01)
    path = paths.resolve(relpath)
    path.write_text(path.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    assert fs.edited_documents("shopee") == (relpath,)


def test_curation_s_own_write_is_not_an_edit(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    _document(curated=True)
    assert fs.edited_documents("shopee") == ()


def test_stamping_changes_nothing_but_the_stamp(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    relpath = _document(body="the original body")
    before = fs.read_file(relpath)
    fs.mark_curated(relpath, when="2026-09-17T00:00:00+00:00")
    after = fs.read_file(relpath)
    assert after.body == before.body
    assert (after.title, after.description, after.actor) == (
        before.title,
        before.description,
        before.actor,
    )
    assert after.created_at == before.created_at
    assert after.curated_at == "2026-09-17T00:00:00+00:00"


def test_stamping_keeps_frontmatter_coffer_did_not_write(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    # A document is a person's as much as Coffer's, and the stamp is Coffer
    # editing it unattended, on a timer. Dropping a key it does not recognise
    # would delete their own `tags:` from under them.
    relpath = _document()
    path = paths.resolve(relpath)
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "actor: user", "actor: user\ntags: [account, session]\nreviewed_by: yuxing"
        ),
        encoding="utf-8",
    )
    fs.mark_curated(relpath)
    frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    assert frontmatter["tags"] == ["account", "session"]
    assert frontmatter["reviewed_by"] == "yuxing"
    assert frontmatter[fs.CURATED_AT_KEY]


def test_a_readme_is_never_owed(knowledge_root) -> None:  # type: ignore[no-untyped-def]
    paths.readme_path("shopee").write_text("# shopee\n\nAbout.\n", encoding="utf-8")
    assert fs.edited_documents("shopee") == ()


def test_a_description_containing_a_rule_does_not_end_the_frontmatter() -> None:
    """A fence only closes the block at column 0.

    PyYAML writes a long or multi-line string as an *indented* continuation, so
    a description whose text contains a horizontal rule puts ``  ---`` inside
    the block. A scan that stripped each line before comparing ended the
    frontmatter there — and because the truncated YAML is then an unterminated
    quote, the mapping degraded to empty and the rest of the metadata leaked
    into the body, where an agent reading the file would be handed it as prose.
    Nothing in the vault trips this today only because every field a knowledge
    file carries is short; a derived document's generated description is the
    one with no such guarantee.
    """
    description = "How the ingest pipeline splits a doc:\n---\nthen re-titles it."
    raw = render_frontmatter(
        {"title": "Ingest", "description": description, "actor": "user"}, "body"
    )
    assert "\n  ---\n" in raw  # the indented continuation this guards against

    frontmatter, body = split_frontmatter(raw)

    assert set(frontmatter) == {"title", "description", "actor"}
    assert frontmatter["description"] == description
    assert body.strip() == "body"
