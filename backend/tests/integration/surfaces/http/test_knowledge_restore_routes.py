"""Undoing a delete of a collection or a document, a collection's description,
and a collection's missing title, observed through the routes (spec knowledge
"Undo a knowledge delete from its toast", "Read a collection's description
from its README", "Cover knowledge management on REST and the CLI").

``client`` (from ``conftest.py``) boots the full app with the knowledge root
under ``tmp_path``; the history is real git under it.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.infrastructure.knowledge.paths import knowledge_root

from .conftest import _create_collection, _submit


def _uid(client, name: str) -> str:  # type: ignore[no-untyped-def]
    rows = client.get("/api/v1/knowledge/collections").json()["collections"]
    return str(next(r["uid"] for r in rows if r["name"] == name))


def _change(client, operation: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    feed = client.get("/api/v1/knowledge/changes").json()["changes"]
    return next(c for c in feed if c["operation"] == operation)


def _edited(client) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/audit", params={"event_type": "knowledge_edited"})
    assert r.status_code == 200, r.text
    return list(r.json()["entries"])


@pytest.mark.acceptance(spec="knowledge", scenario="undo a collection delete")
def test_a_deleted_collection_comes_back_with_its_documents_and_readme(  # type: ignore[no-untyped-def]
    client, tmp_path
) -> None:
    resp = client.post(
        "/api/v1/knowledge/collections", json={"name": "shopee", "description": "Shopee services."}
    )
    assert resp.status_code == 201, resp.text
    doc = _submit(client, collection="shopee", title="Cache", description="d", body="kept text")
    old_uid = _uid(client, "shopee")

    deleted = client.delete(f"/api/v1/resources/{old_uid}")
    assert deleted.status_code in (200, 204), deleted.text
    assert not (knowledge_root() / "shopee").exists()

    # The changes feed lists the delete, with every document it removed.
    removal = _change(client, "remove")
    assert removal["collections"] == ["shopee"]
    assert doc in [d["path"] for d in removal["documents"]]

    restored = client.post(f"/api/v1/knowledge/changes/{removal['version']}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["writer"] == "user"
    assert restored.json()["operation"] == "restore"
    assert restored.json()["restored_from"] == removal["version"]

    rows = client.get("/api/v1/knowledge/collections").json()["collections"]
    row = next(r for r in rows if r["name"] == "shopee")
    assert row["uid"] != old_uid
    assert (row["description"], row["document_count"]) == ("Shopee services.", 1)
    body = client.get("/api/v1/knowledge/file", params={"path": doc}).json()["body"]
    assert body.strip() == "kept text"
    assert any(e["details"].get("restored_from") == removal["version"] for e in _edited(client))

    # A collection of that name is back: a second restore is refused, and writes nothing.
    again = client.post(f"/api/v1/knowledge/changes/{removal['version']}/restore")
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_EXISTS"


@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection undo that fails part-way leaves nothing behind"
)
def test_a_failed_collection_restore_leaves_no_row_and_no_directory(  # type: ignore[no-untyped-def]
    client, monkeypatch
) -> None:
    from coffer.application.knowledge import collection_writes

    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "Shopee."})
    _submit(client, collection="shopee", title="Cache", description="d", body="kept text")
    assert client.delete(f"/api/v1/resources/{_uid(client, 'shopee')}").status_code in (200, 204)
    removal = _change(client, "remove")

    real = collection_writes.collection_files.restore_file
    calls: list[str] = []

    def failing(relpath: str, raw: bytes) -> None:
        calls.append(relpath)
        if len(calls) == 2:
            raise OSError("disk full")
        real(relpath, raw)

    monkeypatch.setattr(collection_writes.collection_files, "restore_file", failing)
    try:
        failed = client.post(f"/api/v1/knowledge/changes/{removal['version']}/restore")
    except OSError:
        failed = None  # the test client re-raises an unhandled server error
    assert failed is None or failed.status_code >= 500
    assert len(calls) == 2
    assert not (knowledge_root() / "shopee").exists()
    rows = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert [r["name"] for r in rows] == []

    monkeypatch.setattr(collection_writes.collection_files, "restore_file", real)
    again = client.post(f"/api/v1/knowledge/changes/{removal['version']}/restore")
    assert again.status_code == 200, again.text
    assert (knowledge_root() / "shopee").is_dir()


@pytest.mark.acceptance(spec="knowledge", scenario="undo a document delete")
def test_a_deleted_document_comes_back_as_a_new_version(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    doc = _submit(client, collection="shopee", title="Cache", description="d", body="first")
    assert client.delete("/api/v1/knowledge/file", params={"path": doc}).status_code == 204

    delete = _change(client, "delete")
    restored = client.post(f"/api/v1/knowledge/changes/{delete['version']}/restore")
    assert restored.status_code == 200, restored.text
    assert [d["path"] for d in restored.json()["documents"]] == [doc]
    read = client.get("/api/v1/knowledge/file", params={"path": doc})
    assert read.status_code == 200 and read.json()["body"].strip() == "first"

    feed = client.get("/api/v1/knowledge/changes", params={"collection": "shopee"}).json()
    ops = [c["operation"] for c in feed["changes"] if doc in [d["path"] for d in c["documents"]]]
    assert ops == ["restore", "delete", "promote"]


@pytest.mark.acceptance(spec="knowledge", scenario="an undo that would overwrite is refused")
def test_a_restore_over_a_document_that_exists_again_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    doc = _submit(client, collection="shopee", title="Cache", description="d", body="first")
    client.delete("/api/v1/knowledge/file", params={"path": doc})
    delete = _change(client, "delete")
    again = _submit(client, collection="shopee", title="Cache", description="d", body="new text")
    assert again == doc

    refused = client.post(f"/api/v1/knowledge/changes/{delete['version']}/restore")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "KNOWLEDGE_RESTORE_CONFLICT"
    assert refused.json()["error"]["details"]["document"] == doc
    body = client.get("/api/v1/knowledge/file", params={"path": doc}).json()["body"]
    assert body.strip() == "new text"

    promote = _change(client, "promote")
    not_a_delete = client.post(f"/api/v1/knowledge/changes/{promote['version']}/restore")
    assert not_a_delete.status_code == 400, not_a_delete.text
    assert not_a_delete.json()["error"]["code"] == "KNOWLEDGE_NOT_A_DELETE"
    # A version that is no knowledge change at all is not a delete either.
    unknown = client.post(f"/api/v1/knowledge/changes/{'0' * 40}/restore")
    assert unknown.status_code == 400, unknown.text
    assert unknown.json()["error"]["code"] == "KNOWLEDGE_NOT_A_DELETE"


@pytest.mark.acceptance(spec="knowledge", scenario="edit a collection's description in place")
def test_describing_a_collection_rewrites_only_the_readme_opening_paragraph(  # type: ignore[no-untyped-def]
    client, tmp_path
) -> None:
    client.post("/api/v1/knowledge/collections", json={"name": "shopee", "description": "Old."})
    readme = knowledge_root() / "shopee" / "README.md"
    readme.write_text("# shopee\n\nOld.\n\n## Conventions\n\nKeep this.\n", encoding="utf-8")

    r = client.put(
        f"/api/v1/knowledge/collections/{_uid(client, 'shopee')}/description",
        json={"description": "Shopee's services and who owns them."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "Shopee's services and who owns them."
    assert readme.read_text(encoding="utf-8") == (
        "# shopee\n\nShopee's services and who owns them.\n\n## Conventions\n\nKeep this.\n"
    )
    listed = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert listed[0]["description"] == "Shopee's services and who owns them."
    assert _edited(client)[-1]["details"]["path"] == "shopee/README.md"
    assert _change(client, "save")["collections"] == ["shopee"]

    empty = client.put(
        f"/api/v1/knowledge/collections/{_uid(client, 'shopee')}/description",
        json={"description": ""},
    )
    assert empty.status_code == 422


@pytest.mark.acceptance(spec="knowledge", scenario="a collection carries no title")
def test_a_collection_has_no_title_on_any_route(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "team")
    row = client.get("/api/v1/knowledge/collections").json()["collections"][0]
    assert "title" not in row

    refused = client.patch(f"/api/v1/resources/{row['uid']}", json={"title": "Team notes"})
    assert refused.status_code == 422, refused.text
    assert client.get(f"/api/v1/resources/{row['uid']}").json()["title"] is None
