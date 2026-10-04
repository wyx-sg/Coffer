"""``/api/v1/knowledge/*`` — the human's side of the directory.

See "Cover knowledge management on REST and the CLI" and "Present a collection as
one tree in the web UI".

These routes serve the person and the web page, never an agent: the agent reads the
files themselves at the paths its delivered skill carries ("Expose exactly one
knowledge tool"). What that leaves this surface responsible for is the part a person
cannot do from a shell without knowing the rules — creating a collection, submitting
new material without choosing where it goes, and being refused when a request aims
at something that is not a document.

A collection is one tree of documents a person and curation write together. New
knowledge never arrives as a file write: an agent's file in the collection's
hidden inbox, or ``/upload``, submits it, and with no internal model configured —
the state of the app booted here — it is promoted to a document on the spot
("Submit every entrance's input as material", "Promote material directly when no
model is configured").
``DELETE`` reaches any document; ``GET`` reads any document and any inbox item;
``PUT`` saves an edited body over an existing document. The README and the inbox are
not documents, and each of those refusals is one assertion below, driven through the
route rather than the service, because the route is where a handler could forget the
rule.

``client``, ``_create_collection``, ``_submit``, ``_submit_material`` and ``_hold_material`` live in
``conftest.py``.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.knowledge import curation_state, fs

from .conftest import _create_collection, _hold_material, _submit, _submit_material


def _document(client: TestClient, collection: str, title: str, body: str = "b") -> str:
    """A document written straight into the tree — what a person's editor or a
    curation pass leaves there. New knowledge reaches a collection as material
    ("Submit every entrance's input as material"); the one route that writes a
    document only replaces the body of one that exists."""
    return fs.write_file(
        directory=collection, title=title, description="written", body=body, curated=True
    ).path


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
    # No lanes: a collection is one tree the person and curation share.
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


def test_the_listing_counts_documents_and_pending_material_apart(  # type: ignore[no-untyped-def]
    client, monkeypatch
) -> None:
    """Material still in the inbox is exactly what an agent cannot read yet,
    and a single total would hide it ("Hide dot-prefixed entries except the inbox")."""
    _create_collection(client, "shopee")
    _submit(client, collection="shopee", title="One", description="d", body="b")
    _document(client, "shopee", "Written")
    _hold_material(monkeypatch)
    assert _submit_material(
        client, collection="shopee", title="Waiting", description="d", body="b"
    ).pending

    listed = client.get("/api/v1/knowledge/collections")
    assert listed.status_code == 200, listed.text
    [entry] = listed.json()["collections"]
    assert (entry["document_count"], entry["pending_count"]) == (2, 1)


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


def test_the_tree_lists_documents_and_the_inbox_but_not_the_readme(  # type: ignore[no-untyped-def]
    client, monkeypatch
) -> None:
    """One tree per collection ("Present a collection as one tree in the web UI").
    The README describes it rather than being content in it, and the inbox is a
    folder of its own, marked so the page shows it read-only ("Hide dot-prefixed
    entries except the inbox", "Keep the collection README out of the corpus")."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "d"})
    document = _submit(client, collection="shopee", title="Note", description="d", body="b")
    _hold_material(monkeypatch)
    _submit_material(client, collection="shopee", title="Waiting", description="d", body="b")

    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"})
    assert level.status_code == 200, level.text
    assert [(f["path"], f["inbox"]) for f in level.json()["files"]] == [(document, False)]
    assert level.json()["directories"] == [
        {"path": "shopee/.inbox", "name": ".inbox", "file_count": 1, "inbox": True}
    ]


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


def test_the_inbox_can_be_listed_and_read_but_nothing_else_hidden(  # type: ignore[no-untyped-def]
    client, monkeypatch, tmp_path
) -> None:
    """A person can see what waits to be merged; nothing else hidden is reachable
    ("Hide dot-prefixed entries except the inbox", "Guard every path through one
    module")."""
    _create_collection(client, "shopee")
    _hold_material(monkeypatch)
    _submit_material(client, collection="shopee", title="Waiting", description="w", body="later")
    (tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / ".scratch").mkdir()
    (tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / ".scratch" / "x.md").write_text(
        "x", encoding="utf-8"
    )

    inbox = client.get("/api/v1/knowledge/tree", params={"path": "shopee/.inbox"})
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["directories"] == []
    [item] = inbox.json()["files"]
    assert (item["path"], item["title"], item["inbox"]) == (
        "shopee/.inbox/waiting.md",
        "Waiting",
        True,
    )

    read = client.get("/api/v1/knowledge/file", params={"path": item["path"]})
    assert read.status_code == 200, read.text
    assert (read.json()["body"].strip(), read.json()["inbox"]) == ("later", True)

    for path in ("shopee/.scratch", "shopee/.scratch/x.md"):
        for route in ("tree", "file"):
            resp = client.get(f"/api/v1/knowledge/{route}", params={"path": path})
            assert resp.status_code == 400, (route, path, resp.text)
            assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"


def test_an_inbox_item_cannot_be_deleted_or_saved(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The inbox is read-only on every surface: no route writes or deletes an
    item ("Hide dot-prefixed entries except the inbox")."""
    _create_collection(client, "shopee")
    _hold_material(monkeypatch)
    _submit_material(client, collection="shopee", title="Waiting", description="w", body="b")
    path = "shopee/.inbox/waiting.md"
    fingerprint = client.get("/api/v1/knowledge/file", params={"path": path}).json()["fingerprint"]

    deleted = client.delete("/api/v1/knowledge/file", params={"path": path})
    saved = client.put(
        "/api/v1/knowledge/file",
        json={"path": path, "body": "edited", "expected_fingerprint": fingerprint},
    )
    for resp in (deleted, saved):
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"
    read = client.get("/api/v1/knowledge/file", params={"path": path})
    assert read.json()["body"].strip() == "b"


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


def test_reading_reports_when_curation_last_saw_the_document(client) -> None:  # type: ignore[no-untyped-def]
    """``curated_at`` is what the page reads to say a document is up to date
    with the rest of the collection, or has been edited since ("Settle an item only
    after its pass completes")."""
    _create_collection(client, "shopee")
    stamped = _document(client, "shopee", "Derived", body="what curation concluded")
    by_hand = fs.write_file(directory="shopee", title="Mine", description="d", body="b").path

    assert client.get("/api/v1/knowledge/file", params={"path": stamped}).json()["curated_at"]
    assert client.get("/api/v1/knowledge/file", params={"path": by_hand}).json()["curated_at"] == ""


def test_reading_a_missing_file_is_not_found(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = client.get("/api/v1/knowledge/file", params={"path": "shopee/nope.md"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_FILE_NOT_FOUND"


# ----- submitting material -------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="with no internal model, pending material becomes documents as it stands",
)
def test_material_becomes_a_document_when_no_model_could_merge_it(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    out = _submit_material(
        client,
        title="Account Gateway",
        description="Where account decisions are made",
        body="The orchestration layer.",
        collection="shopee",
    )
    # No internal model is configured in this app, so nothing would ever merge the
    # material: it is a document the moment it arrives ("Promote material directly
    # when no model is configured").
    assert out.document is not None
    assert out.document.path == "shopee/account-gateway.md"
    assert out.pending is None
    # And nothing is left waiting behind it.
    assert (
        list((tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / ".inbox").iterdir()) == []
    )
    # Stamped, so the sweep does not hand the promoted document straight back.
    read = client.get("/api/v1/knowledge/file", params={"path": out.document.path}).json()
    assert read["curated_at"]


def test_material_waits_in_the_inbox_when_a_pass_could_merge_it(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    _hold_material(monkeypatch)

    out = _submit_material(client, collection="shopee", title="Gateway", description="d", body="b")

    assert (out.pending, out.document) == ("gateway.md", None)
    inbox = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / ".inbox"
    assert [p.name for p in inbox.iterdir()] == ["gateway.md"]
    # And no document yet: a pass writes those.
    assert client.get("/api/v1/knowledge/tree", params={"path": "shopee"}).json()["files"] == []


@pytest.mark.acceptance(
    spec="knowledge", scenario="submitting material announces the collection on the event stream"
)
def test_submitting_material_announces_the_collection_on_the_event_stream(client) -> None:  # type: ignore[no-untyped-def]
    """The inbox count and the documents change with no write to the collection's row,
    so no resource hint fires; the page learns of it from this event."""
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
    # The one route that writes a document only replaces the body of one that exists.
    assert {m for m, p in routes if p == "/api/v1/knowledge/file"} == {"GET", "PUT", "DELETE"}
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


def test_saving_keeps_the_frontmatter_and_audits_the_edit(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """``PUT /file`` replaces the body only ("Save a document edited in the web UI"):
    every frontmatter key — a person's own included — is kept byte for byte, and
    the save is a ``user`` commit whose content curation has not settled, so the
    sweep sees an edit."""
    _create_collection(client, "shopee")
    head = "---\ntitle: Cache\ndescription: How the cache works\ntags:\n- infra\n---"
    on_disk = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "cache.md"
    on_disk.write_text(f"{head}\n\nold body\n", encoding="utf-8")
    path = "shopee/cache.md"
    fs.mark_curated(path)
    assert curation_state.edited_documents("shopee") == ()
    fingerprint = client.get("/api/v1/knowledge/file", params={"path": path}).json()["fingerprint"]

    resp = client.put(
        "/api/v1/knowledge/file",
        json={"path": path, "body": "new body", "expected_fingerprint": fingerprint},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["body"].strip() == "new body"
    assert resp.json()["fingerprint"] != fingerprint
    assert on_disk.read_text(encoding="utf-8") == f"{head}\n\nnew body\n"
    assert curation_state.edited_documents("shopee") == (path,)

    audit = client.get("/api/v1/audit", params={"event_type": "knowledge_edited"})
    assert audit.status_code == 200, audit.text
    assert [e["details"]["path"] for e in audit.json()["entries"]] == [path]


@pytest.mark.parametrize(
    "path",
    ["shopee", "shopee/README.md", "shopee/../outside.md", "shopee/missing.md"],
)
def test_saving_refuses_anything_but_an_existing_document(client, path: str) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = client.put(
        "/api/v1/knowledge/file",
        json={"path": path, "body": "b", "expected_fingerprint": "0" * 64},
    )
    assert resp.status_code in (400, 404), resp.text
    assert resp.json()["error"]["code"] in ("KNOWLEDGE_PATH_UNSAFE", "KNOWLEDGE_FILE_NOT_FOUND")


# ----- deleting a document -------------------------------------------------


def test_deleting_a_document_removes_it_from_disk(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    path = _submit(client, collection="shopee", title="Stale", description="d", body="b")
    on_disk = tmp_path / ".coffer" / "vault" / "knowledge" / path
    assert on_disk.is_file()

    resp = client.delete("/api/v1/knowledge/file", params={"path": path})
    assert resp.status_code == 204, resp.text
    assert not on_disk.exists()


def test_deleting_a_document_curation_wrote_is_allowed(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Per "Let only a person delete a document": the collection is the person's as
    much as curation's, so a document curation wrote is theirs to delete too."""
    _create_collection(client, "shopee")
    derived = _document(client, "shopee/runbooks", "Derived")

    resp = client.delete("/api/v1/knowledge/file", params={"path": derived})
    assert resp.status_code == 204, resp.text
    assert not (tmp_path / ".coffer" / "vault" / "knowledge" / derived).exists()


def test_deleting_the_readme_is_refused(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The README describes the collection rather than being a document in it
    ("Keep the collection README out of the corpus"); removing it goes through the
    editor, not this route."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "d"})

    resp = client.delete("/api/v1/knowledge/file", params={"path": "shopee/README.md"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"
    assert (tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "README.md").is_file()


# ----- curating ------------------------------------------------------------


def test_curating_with_no_model_promotes_what_the_inbox_holds(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    """Material that arrived while a model was configured, and is still waiting
    when there is none, is not stranded: the next pass makes each item a
    document as it stands and says which ("Promote material directly when no model
    is configured")."""
    _create_collection(client, "shopee")
    _hold_material(monkeypatch)
    _submit_material(client, collection="shopee", title="Gateway", description="d", body="b")
    uid = client.get("/api/v1/resources", params={"kind": "knowledge", "name": "shopee"}).json()[
        "resources"
    ][0]["uid"]

    resp = client.post(f"/api/v1/knowledge/collections/{uid}/curate")
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["status"] == "no_model"
    # Curate now answers every pass it ran; with no model the one pass promoted
    # the whole inbox, and the run ends there.
    assert [p["status"] for p in out["passes"]] == ["no_model"]
    assert out["passes"][0]["promoted"] == ["shopee/gateway.md"]
    assert (
        list((tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / ".inbox").iterdir()) == []
    )
    promoted = client.get("/api/v1/knowledge/file", params={"path": "shopee/gateway.md"})
    assert promoted.status_code == 200, promoted.text


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


@pytest.mark.acceptance(
    spec="knowledge", scenario="Curate now is refused while a sync round waits for a person"
)
def test_curate_now_is_refused_while_a_sync_round_waits_for_a_person(  # type: ignore[no-untyped-def]
    client, monkeypatch
) -> None:
    """A rewrite is not piled onto files a person is deciding between ("Never
    overlap a curation pass and a round") — the manual trigger honours that too."""
    from coffer.surfaces.http.knowledge import curation_state

    _create_collection(client, "shopee")
    uid = client.get("/api/v1/resources", params={"kind": "knowledge", "name": "shopee"}).json()[
        "resources"
    ][0]["uid"]

    async def _waiting() -> bool:
        return True

    monkeypatch.setattr(curation_state, "_curation_hold", _waiting)

    resp = client.post(f"/api/v1/knowledge/collections/{uid}/curate")

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_CURATION_HELD"
