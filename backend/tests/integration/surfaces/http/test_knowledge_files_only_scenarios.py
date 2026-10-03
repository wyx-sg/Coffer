"""Knowledge scenarios observed through the web UI's own routes and the files.

``client`` (from ``conftest.py``) boots the full app with ``HOME`` pinned to
``tmp_path``. Specs: knowledge "Create collections only deliberately", "Read a
collection's description from its README", "Submit every entrance's input as
material" and "Let only a person delete a document".
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.intake import adopt_dropped_files
from coffer.infrastructure.knowledge import fs, inbox, paths

from .conftest import _create_collection, _hold_material


def _root(tmp_path):  # type: ignore[no-untyped-def]
    return tmp_path / ".coffer" / "vault" / "knowledge"


@pytest.mark.acceptance(
    spec="knowledge", scenario="an unknown collection is an error, never auto-created"
)
def test_a_read_of_an_unknown_collection_is_a_404_and_creates_nothing(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert not (_root(tmp_path) / "typo").exists()

    for path in ("typo", "typo/inbox-ish"):
        resp = client.get("/api/v1/knowledge/tree", params={"path": path})
        assert resp.status_code == 404, resp.text
    missing = client.get("/api/v1/knowledge/file", params={"path": "typo/note.md"})
    assert missing.status_code == 404, missing.text

    assert not (_root(tmp_path) / "typo").exists(), "a read never provisions a collection"
    assert [
        c["name"] for c in client.get("/api/v1/knowledge/collections").json()["collections"]
    ] == []


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="an upload and an agent's file both leave material in the inbox",
)
def test_an_upload_and_an_agents_file_both_leave_material_in_the_inbox(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    from coffer.surfaces.http.knowledge.dependencies import get_knowledge_service

    _create_collection(client, "shopee")
    _hold_material(monkeypatch)

    uploaded = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("notes.md", b"# Notes\n\nFrom a phone.\n")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["pending"] is True
    assert uploaded.json()["path"] is None

    # An agent writes with its own file tool; the sweep then sees the file.
    directory = paths.inbox_dir("shopee")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent-note.md").write_text("# Agent note\n\nFound in a repo.\n", encoding="utf-8")
    adopted = client.portal.call(adopt_dropped_files, get_knowledge_service())  # type: ignore[union-attr]
    assert adopted == ["shopee/.inbox/agent-note.md"]

    assert sorted(inbox.inbox_items("shopee")) == ["agent-note.md", "notes.md"]
    # Neither entrance added a document to the visible tree.
    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"}).json()
    assert level["files"] == []


@pytest.mark.acceptance(spec="knowledge", scenario="delete a document an agent wrote")
def test_a_person_deletes_a_document_an_agent_wrote(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    first = fs.write_file(
        directory="shopee", title="First", description="d", body="b", actor="agent"
    ).path
    second = fs.write_file(
        directory="shopee", title="Second", description="d", body="b", actor="agent"
    ).path
    for path in (first, second):
        assert (
            client.get("/api/v1/knowledge/file", params={"path": path}).json()["actor"] == "agent"
        )

    deleted = client.delete("/api/v1/knowledge/file", params={"path": first})
    assert deleted.status_code == 204, deleted.text
    (_root(tmp_path) / second).unlink()

    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"}).json()
    assert level["files"] == []
    assert not (_root(tmp_path) / first).exists()
    entries = client.get("/api/v1/audit", params={"limit": 100}).json()["entries"]
    deletions = [e for e in entries if e["event_type"] == "knowledge_deleted"]
    assert len(deletions) == 1


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the catalogue lists collections with their README description",
)
def test_the_catalogue_reads_the_description_off_the_readme(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    created = client.post(
        "/api/v1/knowledge/collections",
        json={"name": "shopee", "description": "First description"},
    )
    assert created.status_code == 201, created.text
    [entry] = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert entry["description"] == "First description"

    (_root(tmp_path) / "shopee" / "README.md").write_text(
        "# shopee\n\nEdited by hand.\n", encoding="utf-8"
    )

    [entry] = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert entry["description"] == "Edited by hand."
