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
to a document on the spot ("Promote submitted material at once").
``DELETE`` reaches any document; ``GET`` reads any document;
``PUT`` saves an edited body over an existing document. The README and the inbox are
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
from starlette.testclient import TestClient

from coffer.infrastructure.knowledge import fs, paths

from .conftest import _create_collection, _submit, _submit_material


def _document(client: TestClient, collection: str, title: str, body: str = "b") -> str:
    """A document written straight into the tree — what a person's editor or an
    agent leaves there. New knowledge reaches a collection as material
    ("Promote submitted material at once"); the one route that writes a
    document only replaces the body of one that exists."""
    return fs.write_file(directory=collection, title=title, description="written", body=body).path


# ----- collections ---------------------------------------------------------


def test_creating_a_collection_creates_one_tree_and_a_readme(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/knowledge/collections",
        json={"name": "shopee", "description": "Internal systems."},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "shopee"

    collection = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee"
    assert collection.is_dir()
    # No lanes: a collection is one tree the person and the agents share.
    assert not (collection / "sources").exists()
    assert not (collection / "topics").exists()
    # The description a caller gave becomes the README, which is where every
    # later read of it comes from ("Read a collection's description from its README").
    assert "Internal systems." in (collection / "README.md").read_text(encoding="utf-8")


def test_creating_the_same_collection_twice_is_a_conflict(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = client.post("/api/v1/knowledge/collections", json={"name": "shopee"})
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_EXISTS"


@pytest.mark.acceptance(spec="knowledge", scenario="a collection read carries its tidy hand-off")
def test_the_listing_counts_documents_and_carries_the_tidy_handoff(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _submit(client, collection="shopee", title="One", description="d", body="b")
    _document(client, "shopee", "Written")

    listed = client.get("/api/v1/knowledge/collections")
    assert listed.status_code == 200, listed.text
    [entry] = listed.json()["collections"]
    assert entry["document_count"] == 2
    assert "pending_count" not in entry
    prompt = entry["tidy_handoff"]["prompt"]
    folder = str(tmp_path / ".coffer" / "vault" / "knowledge" / "shopee")
    assert prompt.startswith(
        "Tidy the knowledge collection `shopee` by following the "
        '"Tidying a collection" section of the coffer-guide skill.'
    )
    assert folder in prompt
    assert "2" in prompt


@pytest.mark.acceptance(
    spec="knowledge", scenario="the knowledge tidy-all hand-off names every collection"
)
def test_the_page_level_tidy_handoff_names_every_collection(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _create_collection(client, "personal")
    _submit(client, collection="shopee", title="One", description="d", body="b")

    resp = client.get("/api/v1/knowledge/tidy-handoff")

    assert resp.status_code == 200, resp.text
    prompt = resp.json()["prompt"]
    root = tmp_path / ".coffer" / "vault" / "knowledge"
    assert prompt.startswith(
        'Tidy every knowledge collection by following the "Tidying a collection" section '
        "of the coffer-guide skill, one collection at a time."
    )
    assert f"- Knowledge root: {root}" in prompt
    assert f"- shopee: {root / 'shopee'} (1 document)" in prompt
    assert f"- personal: {root / 'personal'} (0 documents)" in prompt
    assert 'Read the "Tidying a collection" section of the coffer-guide skill first.' in prompt


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


def test_the_tree_lists_documents_but_neither_the_readme_nor_the_inbox(client) -> None:  # type: ignore[no-untyped-def]
    """One tree per collection ("Show a collection as one tree of read-only
    documents in the web UI"). The README describes it rather than being content
    in it ("Keep the collection README out of the corpus"), and the hidden inbox
    is not listed ("Hide dot-prefixed entries except the inbox")."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "d"})
    document = _submit(client, collection="shopee", title="Note", description="d", body="b")
    inbox_dir = paths.inbox_dir("shopee")
    inbox_dir.mkdir(parents=True, exist_ok=True)
    (inbox_dir / "waiting.md").write_text("waiting\n", encoding="utf-8")

    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"})
    assert level.status_code == 200, level.text
    assert [f["path"] for f in level.json()["files"]] == [document]
    assert level.json()["directories"] == []


def test_a_folder_in_the_collection_is_a_directory_the_tree_offers(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _document(client, "shopee/runbooks", "Note")

    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"}).json()
    assert level["files"] == []
    assert [(d["path"], d["file_count"]) for d in level["directories"]] == [("shopee/runbooks", 1)]


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


def test_no_hidden_entry_is_reachable_and_the_inbox_is_one(  # type: ignore[no-untyped-def]
    client, tmp_path
) -> None:
    """Nothing hidden is listed, read or deleted, the inbox included
    ("Hide dot-prefixed entries except the inbox", "Guard every path through one
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
    assert out["file_path"] == str(
        tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "session.md"
    )
    assert out["folder_path"] == str(tmp_path / ".coffer" / "vault" / "knowledge" / "shopee")
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
    assert out.document.path == "shopee/account-gateway.md"
    inbox = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / ".inbox"
    assert list(inbox.iterdir()) == []


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
    """spec resource-framework "Carry an optional editable title on the kinds that have one":
    ``knowledge`` is not one of them — a collection is shown by its folder
    name, which is also what the file routes take."""
    _create_collection(client, "team")
    rows = client.get("/api/v1/knowledge/collections").json()["collections"]
    row = next(r for r in rows if r["name"] == "team")
    assert "title" not in row

    resp = client.patch(f"/api/v1/resources/{row['uid']}", json={"title": "Team notes"})
    assert resp.status_code == 422, resp.text
