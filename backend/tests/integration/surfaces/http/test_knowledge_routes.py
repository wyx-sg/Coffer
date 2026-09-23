"""``/api/v1/knowledge/*`` — the human's side of the directory (FR-039, FR-040).

These routes serve the person and the web page, never an agent: the agent
reads the files themselves at the paths its delivered skill carries (FR-033).
What that leaves this surface responsible for is the part a person cannot do
from a shell without knowing the rules — creating a collection, submitting new
material without choosing where it goes, and being refused when a request aims
at something that is not a document.

A collection is one tree of documents a person and curation write together.
New knowledge never arrives as a file write: ``POST /material`` submits it to
the collection's hidden inbox, and with no internal model configured — the
state of the app booted here — it is promoted to a document on the spot
(FR-013, FR-029). ``DELETE`` reaches any document; ``GET`` reads any document.
The README and the inbox are not documents, and each of those refusals is one
assertion below, driven through the route rather than the service, because
the route is where a handler could forget the rule.

``client``, ``_create_collection``, ``_submit`` and ``_hold_material`` live in
``conftest.py``.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.knowledge import fs

from .conftest import _create_collection, _hold_material, _submit


def _document(client: TestClient, collection: str, title: str, body: str = "b") -> str:
    """A document written straight into the tree — what a person's editor or a
    curation pass leaves there. No route writes a document, which is the point
    (FR-013)."""
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

    collection = tmp_path / "knowledge" / "shopee"
    assert collection.is_dir()
    # No lanes: a collection is one tree the person and curation share.
    assert not (collection / "sources").exists()
    assert not (collection / "topics").exists()
    # The description a caller gave becomes the README, which is where every
    # later read of it comes from (FR-011).
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
    and a single total would hide it (FR-005)."""
    _create_collection(client, "shopee")
    _submit(client, collection="shopee", title="One", description="d", body="b")
    _document(client, "shopee", "Written")
    _hold_material(monkeypatch)
    held = client.post(
        "/api/v1/knowledge/material",
        json={"collection": "shopee", "title": "Waiting", "description": "d", "body": "b"},
    )
    assert held.status_code == 201, held.text

    listed = client.get("/api/v1/knowledge/collections")
    assert listed.status_code == 200, listed.text
    [entry] = listed.json()["collections"]
    assert (entry["document_count"], entry["pending_count"]) == (2, 1)


def test_the_listing_reads_the_description_off_disk_every_time(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """FR-011: never out of a row — a README edited in an editor is the truth
    the next listing reports."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "First."})
    readme = tmp_path / "knowledge" / "shopee" / "README.md"
    readme.write_text("# shopee\n\nEdited by hand.\n", encoding="utf-8")

    [entry] = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert entry["description"] == "Edited by hand."


# ----- the tree ------------------------------------------------------------


def test_the_tree_lists_documents_but_not_the_readme_or_the_inbox(  # type: ignore[no-untyped-def]
    client, monkeypatch
) -> None:
    """One tree per collection (FR-040). The README describes it rather than
    being content in it, and the inbox is not knowledge yet (FR-005, FR-007)."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "d"})
    document = _submit(client, collection="shopee", title="Note", description="d", body="b")
    _hold_material(monkeypatch)
    client.post(
        "/api/v1/knowledge/material",
        json={"collection": "shopee", "title": "Waiting", "description": "d", "body": "b"},
    )

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
    assert not (tmp_path / "knowledge" / "typo").exists()


def test_a_path_escaping_the_root_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/knowledge/tree", params={"path": "shopee/../../outside"})
    assert resp.status_code in (400, 404), resp.text


def test_the_inbox_is_not_addressable(client) -> None:  # type: ignore[no-untyped-def]
    """Hidden entries are refused by the path guard, so no route can list or
    read material before a pass has merged it (FR-005, FR-006)."""
    _create_collection(client, "shopee")
    resp = client.get("/api/v1/knowledge/tree", params={"path": "shopee/.inbox"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"


# ----- reading a document --------------------------------------------------


def test_reading_carries_the_absolute_paths_the_ui_opens_with(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """FR-041: the page offers open-in-editor and reveal-in-file-manager, and
    neither is possible from a relative path."""
    _create_collection(client, "shopee")
    path = _submit(
        client, collection="shopee", title="Session", description="d", body="account.session"
    )

    resp = client.get("/api/v1/knowledge/file", params={"path": path})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["file_path"] == str(tmp_path / "knowledge" / "shopee" / "session.md")
    assert out["folder_path"] == str(tmp_path / "knowledge" / "shopee")
    assert out["body"].strip() == "account.session"
    assert out["actor"] == "user"


def test_reading_reports_when_curation_last_saw_the_document(client) -> None:  # type: ignore[no-untyped-def]
    """``curated_at`` is what the page reads to say a document is up to date
    with the rest of the collection, or has been edited since (FR-028)."""
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
    scenario="written material waits in the inbox, or becomes a document with no model",
)
def test_material_becomes_a_document_when_no_model_could_merge_it(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/material",
        json={
            "title": "Account Gateway",
            "description": "Where account decisions are made",
            "body": "The orchestration layer.",
            "collection": "shopee",
        },
    )
    assert resp.status_code == 201, resp.text
    out = resp.json()
    # No internal model is configured in this app, so nothing would ever merge
    # the material: it is a document the moment it arrives (FR-029).
    assert out == {
        "status": "written",
        "collection": "shopee",
        "title": "Account Gateway",
        "path": "shopee/account-gateway.md",
    }
    # And nothing is left waiting behind it.
    assert list((tmp_path / "knowledge" / "shopee" / ".inbox").iterdir()) == []
    # Stamped, so the sweep does not hand the promoted document straight back.
    read = client.get("/api/v1/knowledge/file", params={"path": out["path"]}).json()
    assert read["curated_at"]


def test_material_waits_in_the_inbox_when_a_pass_could_merge_it(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    _hold_material(monkeypatch)

    resp = client.post(
        "/api/v1/knowledge/material",
        json={"collection": "shopee", "title": "Gateway", "description": "d", "body": "b"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json() == {
        "status": "pending",
        "collection": "shopee",
        "title": "Gateway",
        "path": None,
    }
    inbox = tmp_path / "knowledge" / "shopee" / ".inbox"
    assert [p.name for p in inbox.iterdir()] == ["gateway.md"]
    # And no document yet: a pass writes those.
    assert client.get("/api/v1/knowledge/tree", params={"path": "shopee"}).json()["files"] == []


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


def test_material_for_an_unknown_collection_is_not_found(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/knowledge/material",
        json={"collection": "typo", "title": "t", "description": "d", "body": "b"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_NOT_FOUND"
    assert not (tmp_path / "knowledge" / "typo").exists()


def test_material_with_no_description_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    """The skill's catalogue is how a document is ever found, so material that
    fails to describe itself is unfindable (FR-003)."""
    _create_collection(client, "shopee")
    resp = client.post(
        "/api/v1/knowledge/material",
        json={"title": "t", "description": "", "body": "b", "collection": "shopee"},
    )
    assert resp.status_code == 422, resp.text


def test_there_is_no_route_that_writes_a_document(client) -> None:  # type: ignore[no-untyped-def]
    """A person edits a document in their own editor; the old write route is
    gone rather than kept as a second way in (FR-013)."""
    _create_collection(client, "shopee")
    resp = client.put(
        "/api/v1/knowledge/file",
        json={"title": "t", "description": "d", "body": "b", "collection": "shopee"},
    )
    assert resp.status_code == 405, resp.text


# ----- deleting a document -------------------------------------------------


def test_deleting_a_document_removes_it_from_disk(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    path = _submit(client, collection="shopee", title="Stale", description="d", body="b")
    on_disk = tmp_path / "knowledge" / path
    assert on_disk.is_file()

    resp = client.delete("/api/v1/knowledge/file", params={"path": path})
    assert resp.status_code == 204, resp.text
    assert not on_disk.exists()


def test_deleting_a_document_curation_wrote_is_allowed(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """FR-020: the collection is the person's as much as curation's, so a
    document curation wrote is theirs to delete too."""
    _create_collection(client, "shopee")
    derived = _document(client, "shopee/runbooks", "Derived")

    resp = client.delete("/api/v1/knowledge/file", params={"path": derived})
    assert resp.status_code == 204, resp.text
    assert not (tmp_path / "knowledge" / derived).exists()


def test_deleting_the_readme_is_refused(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The README describes the collection rather than being a document in it
    (FR-007); removing it goes through the editor, not this route."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "d"})

    resp = client.delete("/api/v1/knowledge/file", params={"path": "shopee/README.md"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"
    assert (tmp_path / "knowledge" / "shopee" / "README.md").is_file()


# ----- curating ------------------------------------------------------------


def test_curating_with_no_model_promotes_what_the_inbox_holds(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    """Material that arrived while a model was configured, and is still waiting
    when there is none, is not stranded: the next pass makes each item a
    document as it stands and says which (FR-029)."""
    _create_collection(client, "shopee")
    _hold_material(monkeypatch)
    client.post(
        "/api/v1/knowledge/material",
        json={"collection": "shopee", "title": "Gateway", "description": "d", "body": "b"},
    )
    uid = client.get("/api/v1/resources", params={"kind": "knowledge", "name": "shopee"}).json()[
        "resources"
    ][0]["uid"]

    resp = client.post(f"/api/v1/knowledge/collections/{uid}/curate")
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["status"] == "no_model"
    assert out["promoted"] == ["shopee/gateway.md"]
    assert list((tmp_path / "knowledge" / "shopee" / ".inbox").iterdir()) == []
    promoted = client.get("/api/v1/knowledge/file", params={"path": "shopee/gateway.md"})
    assert promoted.status_code == 200, promoted.text


def test_the_knowledge_routes_require_the_daemon_token(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/knowledge/collections", headers={"X-Coffer-Token": "wrong"})
    assert resp.status_code == 401
