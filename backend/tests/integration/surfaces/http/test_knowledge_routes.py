"""``/api/v1/knowledge/*`` — the human's side of the directory.

See "Cover knowledge management on REST and the CLI" and "Show a collection as one tree
of documents in the web UI".

These routes serve the person and the web page, never an agent: the agent reads the
files themselves at the paths its delivered skill carries ("Expose exactly one
knowledge tool"). What that leaves this surface responsible for is the part a person
cannot do from a shell without knowing the rules — creating a collection, submitting
new material without choosing where it goes, and being refused when a request aims
at something that is not a document.

A collection is one tree of documents a person and the agents write together. New
knowledge never arrives as a file write: ``/upload`` submits it, and it is promoted
to a document on the spot ("Store an upload the moment it arrives").
``DELETE`` reaches any document; ``GET`` reads any document;
``PUT`` saves an edited body over an existing document. The README and hidden entries are
not documents, and each of those refusals is one assertion below, driven through the
route rather than the service, because the route is where a handler could forget the
rule.

``client``, ``_create_collection``, ``_submit`` and ``_submit_material`` live in
``conftest.py``.
"""

from __future__ import annotations

import os
import pathlib

import pytest
import yaml
from starlette.testclient import TestClient

from coffer.infrastructure.knowledge import fs, paths

from .conftest import _create_collection, _submit, _submit_material


def _document(client: TestClient, collection: str, title: str, body: str = "b") -> str:
    """A page written straight into the collection's ``pages/`` — what a
    person's editor or an agent leaves there. ``collection`` may name a folder
    inside it (``shopee/runbooks`` is ``shopee/pages/runbooks``). New knowledge
    reaches a collection as material ("Store an upload the moment it arrives");
    no route writes a page."""
    name, _, folder = collection.partition("/")
    directory = f"{name}/pages" + (f"/{folder}" if folder else "")
    return fs.write_file(directory=directory, title=title, description="written", body=body).path


def _page(collection: str, slug: str, body: str = "", **front: object) -> str:
    """A page under ``pages/`` with a title and ``front``."""
    fields: dict[str, object] = {"title": slug, **front}
    path = paths.collection_dir(collection) / "pages" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(fields)}---\n\n{body}\n", encoding="utf-8")
    return paths.relative_of(path)


# ----- collections ---------------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge", scenario="a new collection starts from the LLM-wiki template"
)
def test_a_new_collection_starts_from_the_llm_wiki_template(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/knowledge/collections",
        json={"name": "shopee", "description": "How the shop is built."},
    )
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["name"] == "shopee"

    collection = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee"
    assert sorted(p.name for p in collection.iterdir()) == ["AGENTS.md", "README.md", "index.md"]
    readme = (collection / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("---\nrules: AGENTS.md\nentry: index.md\n---\n\n# shopee\n\n")
    assert "How the shop is built." in readme
    # The description a caller gave is read back from the README ("Read a
    # collection's description from its README").
    assert (out["rules_file"], out["entry_file"], out["description"]) == (
        "AGENTS.md",
        "index.md",
        "How the shop is built.",
    )


@pytest.mark.acceptance(spec="knowledge", scenario="a blank collection holds its README alone")
def test_a_blank_collection_holds_its_readme_alone(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/knowledge/collections",
        json={"name": "notes", "description": "My notes.", "template": "blank"},
    )
    assert resp.status_code == 201, resp.text
    collection = tmp_path / ".coffer" / "vault" / "knowledge" / "notes"
    assert [p.name for p in collection.iterdir()] == ["README.md"]
    assert (collection / "README.md").read_text(encoding="utf-8") == "# notes\n\nMy notes.\n"
    assert resp.json()["rules_file"] == "README.md"

    refused = client.post(
        "/api/v1/knowledge/collections", json={"name": "other", "template": "zettel"}
    )
    assert refused.status_code == 422, refused.text
    assert not (tmp_path / ".coffer" / "vault" / "knowledge" / "other").exists()


def test_creating_the_same_collection_twice_is_a_conflict(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = client.post("/api/v1/knowledge/collections", json={"name": "shopee"})
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_EXISTS"


@pytest.mark.acceptance(spec="knowledge", scenario="a collection read carries its tidy hand-off")
def test_the_listing_counts_files_and_carries_the_tidy_handoff(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee", template="llm-wiki")
    _submit(client, collection="shopee", title="One", description="d", body="b")
    _document(client, "shopee", "Written")
    _document(client, "shopee", "Second")

    listed = client.get("/api/v1/knowledge/collections")
    assert listed.status_code == 200, listed.text
    [entry] = listed.json()["collections"]
    # AGENTS.md, index.md, a source and two pages; the README is not counted.
    assert entry["note_count"] == 5
    assert "page_count" not in entry and "source_count" not in entry
    prompt = entry["tidy_handoff"]["prompt"]
    folder = str(tmp_path / ".coffer" / "vault" / "knowledge" / "shopee")
    assert prompt.startswith("Tidy the knowledge collection `shopee` by its own rules file")
    assert '"Tidying a collection"' in prompt
    assert f"- Path: {folder}" in prompt
    assert "- Rules file: AGENTS.md" in prompt
    assert "- Markdown files: 5" in prompt
    assert "- Broken links: none" in prompt


@pytest.mark.acceptance(
    spec="knowledge", scenario="the knowledge tidy-all hand-off names every collection"
)
def test_the_page_level_tidy_handoff_names_every_collection(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _create_collection(client, "personal")
    _submit(client, collection="shopee", title="One", description="d", body="b")
    for title in ("A", "B", "C"):
        _document(client, "shopee", title)
    _document(client, "personal", "Mine")

    resp = client.get("/api/v1/knowledge/tidy-handoff")

    assert resp.status_code == 200, resp.text
    prompt = resp.json()["prompt"]
    root = tmp_path / ".coffer" / "vault" / "knowledge"
    assert prompt.startswith("Tidy every knowledge collection, one collection at a time")
    assert '"Tidying a collection"' in prompt
    assert f"- Knowledge root: {root}" in prompt
    assert f"- shopee: {root / 'shopee'} (4 Markdown files, 0 broken links)" in prompt
    assert f"- personal: {root / 'personal'} (1 Markdown file, 0 broken links)" in prompt


def _listed(client: TestClient) -> dict[str, dict]:  # type: ignore[type-arg]
    found = client.get("/api/v1/knowledge/collections").json()["collections"]
    return {c["name"]: c for c in found}


@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection lists when its newest document was written"
)
def test_the_listing_carries_when_the_newest_document_was_written(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _create_collection(client, "empty")
    older = _document(client, "shopee", "Older")
    newer = _document(client, "shopee", "Newer")

    listed = _listed(client)
    folder = pathlib.Path(listed["shopee"]["folder_path"])
    os.utime(folder.parent / older, (1_700_000_000, 1_700_000_000))
    os.utime(folder.parent / newer, (1_800_000_000, 1_800_000_000))

    listed = _listed(client)
    assert listed["shopee"]["updated_at"] == "2027-01-15T08:00:00+00:00"
    assert listed["empty"]["updated_at"] is None


def test_the_listing_reads_the_description_off_disk_every_time(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Per "Read a collection's description from its README": never out of a row — a
    README edited in an editor is the truth the next listing reports."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "First."})
    readme = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "README.md"
    readme.write_text("# shopee\n\nEdited by hand.\n", encoding="utf-8")

    [entry] = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert entry["description"] == "Edited by hand."


# ----- the tree ------------------------------------------------------------


def test_the_tree_lists_documents_and_the_readme_but_no_hidden_folder(client) -> None:  # type: ignore[no-untyped-def]
    """One tree per collection ("Show a collection as one tree of read-only
    documents in the web UI"). The README is listed as the plain file it is —
    readable, never a page or a source ("Keep the collection README out of
    counts and curation") — and a hidden folder is not listed ("Hide
    dot-prefixed entries")."""
    _create_collection(client, "shopee")
    document = _submit(client, collection="shopee", title="Note", description="d", body="b")
    hidden = paths.collection_dir("shopee") / ".inbox"
    hidden.mkdir(parents=True, exist_ok=True)
    (hidden / "waiting.md").write_text("waiting\n", encoding="utf-8")

    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"})
    assert level.status_code == 200, level.text
    assert [f["path"] for f in level.json()["files"]] == ["shopee/README.md"]
    assert [d["path"] for d in level.json()["directories"]] == ["shopee/sources"]
    sources = client.get("/api/v1/knowledge/tree", params={"path": "shopee/sources"}).json()
    assert [f["path"] for f in sources["files"]] == [document]


def test_a_folder_in_the_collection_is_a_directory_the_tree_offers(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _document(client, "shopee/runbooks", "Note")

    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee/pages"}).json()
    assert level["files"] == []
    assert [(d["path"], d["file_count"]) for d in level["directories"]] == [
        ("shopee/pages/runbooks", 1)
    ]


def test_the_tree_of_an_unknown_collection_is_not_found_and_creates_nothing(  # type: ignore[no-untyped-def]
    client, tmp_path
) -> None:
    resp = client.get("/api/v1/knowledge/tree", params={"path": "typo"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_NOT_FOUND"
    assert not (tmp_path / ".coffer" / "vault" / "knowledge" / "typo").exists()


def test_a_path_escaping_the_root_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/knowledge/tree", params={"path": "shopee/../../outside"})
    assert resp.status_code in (400, 404), resp.text


def test_no_hidden_entry_is_reachable(  # type: ignore[no-untyped-def]
    client, tmp_path
) -> None:
    """Nothing hidden is listed, read or deleted, a folder named ``.inbox`` included
    ("Hide every dot-prefixed entry", "Guard every path through one
    module")."""
    _create_collection(client, "shopee")
    root = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee"
    (root / ".scratch").mkdir()
    (root / ".scratch" / "x.md").write_text("x", encoding="utf-8")
    (root / ".inbox").mkdir()
    (root / ".inbox" / "waiting.md").write_text("later", encoding="utf-8")

    for path in (
        "shopee/.scratch",
        "shopee/.scratch/x.md",
        "shopee/.inbox",
        "shopee/.inbox/waiting.md",
    ):
        for route in ("tree", "file"):
            resp = client.get(f"/api/v1/knowledge/{route}", params={"path": path})
            assert resp.status_code == 400, (route, path, resp.text)
            assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"
    deleted = client.delete("/api/v1/knowledge/file", params={"path": "shopee/.inbox/waiting.md"})
    assert deleted.status_code == 400, deleted.text
    assert deleted.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"
    assert (root / ".inbox" / "waiting.md").read_text(encoding="utf-8") == "later"


# ----- reading a document --------------------------------------------------


def test_reading_carries_the_absolute_paths_the_ui_opens_with(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Per "Return absolute paths on reads": the page offers open-in-editor and
    reveal-in-file-manager, and neither is possible from a relative path."""
    _create_collection(client, "shopee")
    path = _submit(
        client, collection="shopee", title="Session", description="d", body="account.session"
    )

    resp = client.get("/api/v1/knowledge/file", params={"path": path})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    sources = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "sources"
    assert out["file_path"] == str(sources / "session.md")
    assert out["folder_path"] == str(sources)
    assert "kind" not in out and "waiting" not in out
    assert out["body"].strip() == "account.session"
    assert out["actor"] == "user"


def test_reading_a_missing_file_is_not_found(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = client.get("/api/v1/knowledge/file", params={"path": "shopee/nope.md"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_FILE_NOT_FOUND"


# ----- submitting material -------------------------------------------------


def test_material_becomes_a_document_on_arrival(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    out = _submit_material(
        client,
        title="Account Gateway",
        description="Where account decisions are made",
        body="The orchestration layer.",
        collection="shopee",
    )
    # Nothing waits: the material is a document the moment it arrives ("Promote submitted
    # material at once").
    assert out.document.path == "shopee/sources/account-gateway.md"
    assert not (tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / ".inbox").exists()


@pytest.mark.acceptance(
    spec="knowledge", scenario="submitting material announces the collection on the event stream"
)
def test_submitting_material_announces_the_collection_on_the_event_stream(client) -> None:  # type: ignore[no-untyped-def]
    """The documents change with no write to the collection's row, so no resource
    hint fires; the page learns of it from this event."""
    from coffer.surfaces.http.event_dependencies import get_event_broker

    _create_collection(client, "shopee")
    uid = client.get("/api/v1/resources", params={"kind": "knowledge", "name": "shopee"}).json()[
        "resources"
    ][0]["uid"]
    before = get_event_broker().head

    _submit(client, collection="shopee", title="Gateway", description="d", body="b")

    announced = [e for e in get_event_broker().buffered if e.seq > before]
    assert [(e.kind, e.id) for e in announced if e.kind == "knowledge"][-1] == ("knowledge", uid)


def test_two_submissions_of_one_title_are_two_pieces_of_material(client) -> None:  # type: ignore[no-untyped-def]
    """Material is never written over: a second note with the same title is
    more knowledge, not a replacement of the first."""
    _create_collection(client, "shopee")
    first = _submit(client, collection="shopee", title="Session", description="d", body="old")
    second = _submit(client, collection="shopee", title="Session", description="d", body="new")

    assert first != second
    assert client.get("/api/v1/knowledge/file", params={"path": first}).json()["body"].strip() == (
        "old"
    )


def test_material_for_an_unknown_collection_is_refused_and_creates_nothing(
    client, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from coffer.domain.knowledge.errors import CollectionNotFound

    with pytest.raises(CollectionNotFound):
        _submit_material(client, collection="typo", title="t", description="d", body="b")
    assert not (tmp_path / ".coffer" / "vault" / "knowledge" / "typo").exists()


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the routes are the web UI's, with no material or create-at-path route",
)
def test_there_is_no_material_route_and_no_create_at_path_route(client) -> None:  # type: ignore[no-untyped-def]
    routes = {
        (method.upper(), path)
        for path, operations in client.app.openapi()["paths"].items()  # type: ignore[attr-defined]
        if path.startswith("/api/v1/knowledge")
        for method in operations
    }
    assert ("POST", "/api/v1/knowledge/collections") in routes  # the table is not empty
    assert not [p for _, p in routes if p.endswith("/material")]
    # No route saves a document, and none lists, diffs or restores a version of one.
    assert {m for m, p in routes if p == "/api/v1/knowledge/file"} == {"GET", "DELETE"}
    assert not [p for _, p in routes if "/history" in p]
    assert client.post("/api/v1/knowledge/material", json={}).status_code in (404, 405)


def test_a_collection_description_of_only_spaces_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    uid = client.get("/api/v1/resources", params={"kind": "knowledge", "name": "shopee"}).json()[
        "resources"
    ][0]["uid"]
    resp = client.put(
        f"/api/v1/knowledge/collections/{uid}/description", json={"description": "  "}
    )
    assert resp.status_code == 422, resp.text


# ----- deleting a document -------------------------------------------------


def test_deleting_a_document_removes_it_from_disk(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    path = _submit(client, collection="shopee", title="Stale", description="d", body="b")
    on_disk = tmp_path / ".coffer" / "vault" / "knowledge" / path
    assert on_disk.is_file()

    resp = client.delete("/api/v1/knowledge/file", params={"path": path})
    assert resp.status_code == 204, resp.text
    assert not on_disk.exists()


def test_deleting_a_document_an_agent_wrote_is_allowed(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Per "Let only a person delete a document": the collection is the person's, so a
    document an agent wrote is theirs to delete too."""
    _create_collection(client, "shopee")
    derived = _document(client, "shopee/runbooks", "Derived")

    resp = client.delete("/api/v1/knowledge/file", params={"path": derived})
    assert resp.status_code == 204, resp.text
    assert not (tmp_path / ".coffer" / "vault" / "knowledge" / derived).exists()


def test_deleting_the_readme_is_refused(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The README describes the collection rather than being a document in it
    ("Keep the collection README out of the corpus"); removing it is a change
    made in the person's editor, not through this route."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "d"})

    resp = client.delete("/api/v1/knowledge/file", params={"path": "shopee/README.md"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"
    assert (tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "README.md").is_file()


def test_the_knowledge_routes_require_the_daemon_token(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/knowledge/collections", headers={"X-Coffer-Token": "wrong"})
    assert resp.status_code == 401


def test_collection_list_carries_no_title(client) -> None:  # type: ignore[no-untyped-def]
    """A collection is shown by its folder name, which is also what the file
    routes take."""
    _create_collection(client, "team")
    rows = client.get("/api/v1/knowledge/collections").json()["collections"]
    row = next(r for r in rows if r["name"] == "team")
    assert "title" not in row


# ----- the wiki: links, sources and the check -------------------------------


def _uid(client: TestClient, name: str) -> str:
    return client.get("/api/v1/resources", params={"kind": "knowledge", "name": name}).json()[
        "resources"
    ][0]["uid"]


@pytest.mark.acceptance(spec="knowledge", scenario="a file resolves its links")
def test_reading_a_file_resolves_its_links(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _page("shopee", "session-ownership", aliases=["sessions"])
    page = _page(
        "shopee", "overview", "[[sessions|the session service]], [[gone]] and [it](missing.md)"
    )

    out = client.get("/api/v1/knowledge/file", params={"path": page}).json()

    assert "sources" not in out and "page_type" not in out
    assert out["links"] == [
        {
            "target": "sessions",
            "path": "shopee/pages/session-ownership.md",
            "ambiguous": False,
            "kind": "wiki",
            "outside": False,
        },
        {"target": "gone", "path": None, "ambiguous": False, "kind": "wiki", "outside": False},
        {
            "target": "missing.md",
            "path": None,
            "ambiguous": False,
            "kind": "path",
            "outside": False,
        },
    ]


def test_a_file_in_the_uploads_folder_reads_no_wiki_links(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    source = _submit(client, collection="shopee", title="Macro", description="d", body="[[TD-1")
    (paths.knowledge_root() / source).write_text("---\ntitle: Macro\n---\n\n[[TD-1]]\n")

    assert client.get("/api/v1/knowledge/file", params={"path": source}).json()["links"] == []


@pytest.mark.acceptance(spec="knowledge", scenario="a collection's check lists its broken links")
def test_the_check_route_lists_broken_links_and_changes_nothing(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _page("shopee", "a", "[[nowhere]] [[design]]")
    root = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee"
    (root / "plain.md").write_text("No frontmatter, and nothing links here.\n", encoding="utf-8")
    for folder in ("research", "notes"):
        (root / folder).mkdir()
        (root / folder / "design.md").write_text("# Design\n", encoding="utf-8")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    resp = client.get(f"/api/v1/knowledge/collections/{_uid(client, 'shopee')}/check")

    assert resp.status_code == 200, resp.text
    found = [(f["kind"], f["path"], f["target"]) for f in resp.json()["findings"]]
    assert found == [
        ("dead_link", "shopee/pages/a.md", "nowhere"),
        ("ambiguous_link", "shopee/pages/a.md", "design"),
    ]
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    [listed] = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert listed["finding_count"] == 2
    assert resp.json()["collection"]["finding_count"] == listed["finding_count"]


def test_the_check_of_an_unknown_uid_is_not_found(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/knowledge/collections/no-such-uid/check")
    assert resp.status_code == 404, resp.text


@pytest.mark.acceptance(
    spec="knowledge", scenario="the tidy hand-off carries the findings and the tidy commands"
)
def test_the_tidy_handoff_carries_the_findings_and_the_tidy_commands(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _page("shopee", "a", "[[gone]]")

    [entry] = client.get("/api/v1/knowledge/collections").json()["collections"]
    prompt = entry["tidy_handoff"]["prompt"]

    folder = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee"
    assert f"- Path: {folder}" in prompt
    assert "- dead_link: shopee/pages/a.md → gone" in prompt
    assert "`coffer knowledge tidy-start <collection>`" in prompt
    assert "`coffer knowledge tidy-finish <collection>" in prompt
    assert "check_handoff" not in entry
