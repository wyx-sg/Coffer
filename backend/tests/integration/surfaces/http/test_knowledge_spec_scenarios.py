"""Knowledge scenarios observed through ``/api/v1/knowledge``.

``client`` (from ``conftest.py``) boots the full app with
``HOME`` pinned to ``tmp_path`` and no internal model, so
submitted material is promoted to a document as it arrives.
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.knowledge import fs, inbox
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

from .conftest import _create_collection, _hold_material, _submit


@pytest.mark.acceptance(
    spec="knowledge", scenario="name a file by its title and suffix a collision"
)
def test_two_documents_of_one_title_get_a_slug_and_a_suffix(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    first = _submit(
        client, collection="shopee", title="Session Ownership", description="d", body="one"
    )
    second = _submit(
        client, collection="shopee", title="Session Ownership", description="d", body="two"
    )

    assert (first, second) == ("shopee/session-ownership.md", "shopee/session-ownership-2.md")
    for relpath in (first, second):
        frontmatter, _ = split_frontmatter(
            (tmp_path / ".coffer" / "vault" / "knowledge" / relpath).read_text(encoding="utf-8")
        )
        assert "id" not in frontmatter


@pytest.mark.acceptance(spec="knowledge", scenario="leave hidden entries out of every listing")
def test_hidden_entries_are_in_no_listing_count_or_catalogue(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    document = _submit(client, collection="shopee", title="Gateway", description="d", body="b")
    scratch = tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / ".scratch" / "hidden.md"
    scratch.parent.mkdir(parents=True)
    scratch.write_text("---\ntitle: Hidden\ndescription: d\n---\n\nb\n", encoding="utf-8")
    _hold_material(monkeypatch)
    waiting = client.post(
        "/api/v1/knowledge/material",
        json={"collection": "shopee", "title": "Waiting", "description": "d", "body": "b"},
    )
    assert waiting.status_code == 201, waiting.text

    [entry] = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert entry["document_count"] == 1

    from coffer.infrastructure.knowledge import catalogue, paths

    walked = catalogue.walk_files(paths.collection_dir("shopee"))
    assert [f.path for f in walked] == [document]

    # The tree names the document and the inbox — and nothing from `.scratch/`.
    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"}).json()
    assert [f["path"] for f in level["files"]] == [document]
    assert [(d["path"], d["file_count"]) for d in level["directories"]] == [("shopee/.inbox", 1)]
    [item] = inbox.inbox_items("shopee")
    listed = client.get("/api/v1/knowledge/tree", params={"path": "shopee/.inbox"}).json()
    assert [f["path"] for f in listed["files"]] == [f"shopee/.inbox/{item}"]
    read = client.get("/api/v1/knowledge/file", params={"path": f"shopee/.inbox/{item}"})
    assert read.status_code == 200, read.text
    assert read.json()["title"] == "Waiting"
    refused = client.get("/api/v1/knowledge/file", params={"path": "shopee/.scratch/hidden.md"})
    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"


@pytest.mark.acceptance(spec="knowledge", scenario="save an edited body and refuse a stale one")
def test_a_save_keeps_frontmatter_and_a_stale_one_is_refused(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    written = fs.write_file(
        directory="shopee/infra",
        title="Cache",
        description="How the cache works",
        body="first",
        curated=True,
    )
    assert written.path == "shopee/infra/cache.md"
    loaded = client.get("/api/v1/knowledge/file", params={"path": written.path}).json()

    first = client.put(
        "/api/v1/knowledge/file",
        json={
            "path": written.path,
            "body": "second",
            "expected_fingerprint": loaded["fingerprint"],
        },
    )
    assert first.status_code == 200, first.text
    saved = first.json()
    assert (saved["title"], saved["description"]) == ("Cache", "How the cache works")
    assert saved["body"].strip() == "second"
    assert saved["fingerprint"] not in ("", loaded["fingerprint"])

    stale = client.put(
        "/api/v1/knowledge/file",
        json={
            "path": written.path,
            "body": "third",
            "expected_fingerprint": loaded["fingerprint"],
        },
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "KNOWLEDGE_FILE_CONFLICT"
    on_disk = (tmp_path / ".coffer" / "vault" / "knowledge" / written.path).read_text(
        encoding="utf-8"
    )
    frontmatter, body = split_frontmatter(on_disk)
    assert body.strip() == "second"
    assert frontmatter["title"] == "Cache"


@pytest.mark.acceptance(
    spec="knowledge", scenario="a read answers with the file's and its folder's absolute paths"
)
def test_a_nested_read_carries_absolute_file_and_folder_paths(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    written = fs.write_file(
        directory="shopee/infra", title="Cache", description="d", body="b", curated=True
    )
    assert written.path == "shopee/infra/cache.md"

    resp = client.get("/api/v1/knowledge/file", params={"path": written.path})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["file_path"] == str(
        tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "infra" / "cache.md"
    )
    assert out["folder_path"] == str(
        tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "infra"
    )
