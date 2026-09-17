"""``/api/v1/knowledge/*`` — the human's side of the directory (FR-039, FR-040).

These routes serve the person and the web page, never an agent: the agent
reads the files themselves at the paths its delivered skill carries (FR-033).
What that leaves this surface responsible for is the part a person cannot do
from a shell without knowing the rules — creating a collection with both
lanes, writing a source without spelling the lane, and being refused when a
request aims at ``topics/``.

Lane enforcement is the reason most of these exist. ``PUT`` and ``DELETE``
reach ``sources/`` and only ``sources/``; ``GET`` is lane-agnostic because the
page previews a topic document exactly as it previews a source and refuses to
*edit* it instead. Each of those is one assertion below, driven through the
route rather than the service, because the route is where a handler could
forget the rule.

``client``, ``_create_collection`` and ``_write_source`` live in ``conftest.py``.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from coffer.infrastructure.knowledge import fs

from .conftest import _create_collection, _write_source


def _topic(client: TestClient, collection: str, title: str, body: str = "b") -> str:
    """A topic document, written the only way anything writes one — straight
    into the lane. No route offers this, which is the point (FR-021)."""
    return fs.write_file(
        directory=f"{collection}/topics", title=title, description="derived", body=body
    ).path


# ----- collections ---------------------------------------------------------


def test_creating_a_collection_creates_both_lanes_and_a_readme(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/knowledge/collections",
        json={"name": "shopee", "description": "Internal systems."},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "shopee"

    collection = tmp_path / "knowledge" / "shopee"
    assert (collection / "sources").is_dir()
    assert (collection / "topics").is_dir()
    # The description a caller gave becomes the README, which is where every
    # later read of it comes from (FR-011).
    assert "Internal systems." in (collection / "README.md").read_text(encoding="utf-8")


def test_creating_the_same_collection_twice_is_a_conflict(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = client.post("/api/v1/knowledge/collections", json={"name": "shopee"})
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_EXISTS"


def test_the_listing_counts_the_two_lanes_apart(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A collection with sources and no topics is one curation has not reached
    yet, and a single total would hide exactly that (FR-001)."""
    _create_collection(client, "shopee")
    _write_source(client, collection="shopee", title="One", description="d", body="b")
    _topic(client, "shopee", "Derived")
    _topic(client, "shopee", "Also derived")

    listed = client.get("/api/v1/knowledge/collections")
    assert listed.status_code == 200, listed.text
    [entry] = listed.json()["collections"]
    assert (entry["source_count"], entry["topic_count"]) == (1, 2)


def test_the_listing_reads_the_description_off_disk_every_time(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """FR-011: never out of a row — a README edited in an editor is the truth
    the next listing reports."""
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "First."})
    readme = tmp_path / "knowledge" / "shopee" / "README.md"
    readme.write_text("# shopee\n\nEdited by hand.\n", encoding="utf-8")

    [entry] = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert entry["description"] == "Edited by hand."


# ----- the tree ------------------------------------------------------------


def test_the_tree_is_asked_for_one_lane_at_a_time(client) -> None:  # type: ignore[no-untyped-def]
    """The page draws two trees (FR-040), so the lane is part of the path it
    asks for rather than a parameter this route invents."""
    _create_collection(client, "shopee")
    source = _write_source(client, collection="shopee", title="Note", description="d", body="b")
    topic = _topic(client, "shopee", "Derived")

    sources = client.get("/api/v1/knowledge/tree", params={"path": "shopee/sources"})
    topics = client.get("/api/v1/knowledge/tree", params={"path": "shopee/topics"})
    assert sources.status_code == 200 and topics.status_code == 200
    assert [f["path"] for f in sources.json()["files"]] == [source]
    assert [f["path"] for f in topics.json()["files"]] == [topic]


def test_a_folder_inside_the_lane_is_a_directory_the_tree_offers(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _write_source(
        client, collection="shopee", title="Note", description="d", body="b", folder="runbooks"
    )

    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee/sources"}).json()
    assert level["files"] == []
    assert [(d["path"], d["file_count"]) for d in level["directories"]] == [
        ("shopee/sources/runbooks", 1)
    ]


def test_the_tree_of_an_unknown_collection_is_not_found_and_creates_nothing(  # type: ignore[no-untyped-def]
    client, tmp_path
) -> None:
    resp = client.get("/api/v1/knowledge/tree", params={"path": "typo/sources"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_NOT_FOUND"
    assert not (tmp_path / "knowledge" / "typo").exists()


def test_a_path_escaping_the_root_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/knowledge/tree", params={"path": "shopee/../../outside"})
    assert resp.status_code in (400, 404), resp.text


# ----- reading a file ------------------------------------------------------


def test_reading_carries_the_absolute_paths_the_ui_opens_with(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """FR-041: the page offers open-in-editor and reveal-in-file-manager, and
    neither is possible from a relative path."""
    _create_collection(client, "shopee")
    path = _write_source(
        client, collection="shopee", title="Session", description="d", body="account.session"
    )

    resp = client.get("/api/v1/knowledge/file", params={"path": path})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["file_path"] == str(tmp_path / "knowledge" / "shopee" / "sources" / "session.md")
    assert out["folder_path"] == str(tmp_path / "knowledge" / "shopee" / "sources")
    assert out["body"].strip() == "account.session"
    assert out["actor"] == "user"


def test_reading_is_lane_agnostic(client) -> None:  # type: ignore[no-untyped-def]
    """The page previews a topic document exactly as it previews a source; what
    it withholds from a topic is editing, not viewing (FR-040)."""
    _create_collection(client, "shopee")
    topic = _topic(client, "shopee", "Derived", body="what curation concluded")

    resp = client.get("/api/v1/knowledge/file", params={"path": topic})
    assert resp.status_code == 200, resp.text
    assert resp.json()["body"].strip() == "what curation concluded"


def test_reading_a_missing_file_is_not_found(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = client.get("/api/v1/knowledge/file", params={"path": "shopee/sources/nope.md"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_FILE_NOT_FOUND"


# ----- writing a source ----------------------------------------------------


def test_a_write_names_a_collection_and_lands_in_its_sources_lane(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    resp = client.put(
        "/api/v1/knowledge/file",
        json={
            "title": "Account Gateway",
            "description": "Where account decisions are made",
            "body": "The orchestration layer.",
            "collection": "shopee",
        },
    )
    assert resp.status_code == 200, resp.text
    # The caller never spelled `sources/`; the service added it (FR-013).
    assert resp.json()["path"] == "shopee/sources/account-gateway.md"


def test_a_write_by_path_replaces_the_source_there(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    path = _write_source(client, collection="shopee", title="Session", description="d", body="old")

    resp = client.put(
        "/api/v1/knowledge/file",
        json={"title": "Session", "description": "d", "body": "new", "path": path},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["path"] == path
    assert client.get("/api/v1/knowledge/file", params={"path": path}).json()["body"].strip() == (
        "new"
    )


def test_a_write_aimed_at_the_topics_lane_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    """FR-021: curation is the only writer of ``topics/``. The refusal comes
    from path construction, not from a check this handler remembers."""
    _create_collection(client, "shopee")
    topic = _topic(client, "shopee", "Derived")

    resp = client.put(
        "/api/v1/knowledge/file",
        json={"title": "Derived", "description": "d", "body": "hand-edited", "path": topic},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"
    # And nothing was written through: the document is what curation left.
    assert client.get("/api/v1/knowledge/file", params={"path": topic}).json()["body"].strip() == (
        "b"
    )


def test_a_write_naming_both_a_collection_and_a_path_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = client.put(
        "/api/v1/knowledge/file",
        json={
            "title": "t",
            "description": "d",
            "body": "b",
            "collection": "shopee",
            "path": "shopee/sources/t.md",
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"


def test_a_write_with_no_description_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    """The skill's catalogue is how a document is ever found, so a file that
    fails to describe itself is unfindable (FR-003)."""
    _create_collection(client, "shopee")
    resp = client.put(
        "/api/v1/knowledge/file",
        json={"title": "t", "description": "", "body": "b", "collection": "shopee"},
    )
    assert resp.status_code == 422, resp.text


# ----- deleting a source ---------------------------------------------------


def test_deleting_a_source_removes_it_from_disk(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    path = _write_source(client, collection="shopee", title="Stale", description="d", body="b")
    on_disk = tmp_path / "knowledge" / path
    assert on_disk.is_file()

    resp = client.delete("/api/v1/knowledge/file", params={"path": path})
    assert resp.status_code == 204, resp.text
    assert not on_disk.exists()


def test_deleting_a_topic_document_is_refused(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """FR-020: a topic is derived. Deleting one by hand would offer a delete
    the next pass silently undoes, so the path layer refuses it."""
    _create_collection(client, "shopee")
    topic = _topic(client, "shopee", "Derived")

    resp = client.delete("/api/v1/knowledge/file", params={"path": topic})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"
    assert (tmp_path / "knowledge" / topic).is_file()


def test_the_knowledge_routes_require_the_daemon_token(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/knowledge/collections", headers={"X-Coffer-Token": "wrong"})
    assert resp.status_code == 401
