"""Knowledge scenarios observed through ``/api/v1/knowledge``.

``client`` (from ``conftest.py``) boots the full app with
``COFFER_KNOWLEDGE_ROOT`` pinned under ``tmp_path`` and no internal model, so
submitted material is promoted to a document as it arrives.
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.knowledge import fs
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
            (tmp_path / "knowledge" / relpath).read_text(encoding="utf-8")
        )
        assert "id" not in frontmatter


@pytest.mark.acceptance(spec="knowledge", scenario="leave hidden entries out of every listing")
def test_hidden_entries_are_in_no_listing_count_or_catalogue(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    document = _submit(client, collection="shopee", title="Gateway", description="d", body="b")
    scratch = tmp_path / "knowledge" / "shopee" / ".scratch" / "hidden.md"
    scratch.parent.mkdir(parents=True)
    scratch.write_text("---\ntitle: Hidden\ndescription: d\n---\n\nb\n", encoding="utf-8")
    _hold_material(monkeypatch)
    waiting = client.post(
        "/api/v1/knowledge/material",
        json={"collection": "shopee", "title": "Waiting", "description": "d", "body": "b"},
    )
    assert waiting.status_code == 201, waiting.text

    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"}).json()
    assert [f["path"] for f in level["files"]] == [document]
    assert level["directories"] == []
    [entry] = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert entry["document_count"] == 1

    from coffer.infrastructure.knowledge import catalogue, paths

    walked = catalogue.walk_files(paths.collection_dir("shopee"))
    assert [f.path for f in walked] == [document]

    [item] = fs.inbox_items("shopee")
    refused = client.get("/api/v1/knowledge/file", params={"path": f"shopee/.inbox/{item}"})
    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["code"] == "KNOWLEDGE_PATH_UNSAFE"


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
    assert out["file_path"] == str(tmp_path / "knowledge" / "shopee" / "infra" / "cache.md")
    assert out["folder_path"] == str(tmp_path / "knowledge" / "shopee" / "infra")
