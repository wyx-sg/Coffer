"""``/api/v1/knowledge/changes``, the feed a delete's Undo reads, observed
through the routes (spec knowledge "Follow edits across collections in one
feed", "Commit every knowledge write naming its writer").

``client`` (from ``conftest.py``) boots the full app with the knowledge root
under ``tmp_path``; the history is real git under it.
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.sweep import sweep_once
from coffer.infrastructure.knowledge import paths

from .conftest import _create_collection, _submit


def test_the_feed_lists_a_promoted_upload(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _submit(client, collection="shopee", title="Cache", description="d", body="first")
    feed = client.get("/api/v1/knowledge/changes").json()
    promote = next(c for c in feed["changes"] if c["operation"] == "promote")
    assert [d["path"] for d in promote["documents"]] == ["shopee/cache.md"]


@pytest.mark.acceptance(spec="knowledge", scenario="recent changes lists edits across collections")
def test_the_feed_lists_edits_across_collections_newest_first(client) -> None:  # type: ignore[no-untyped-def]
    from coffer.surfaces.http.knowledge.dependencies import get_knowledge_service

    async def _no_refresh() -> None:
        return None

    _create_collection(client, "shopee")
    _create_collection(client, "personal")
    # An agent's edit on disk, in another collection, found by the sweep …
    (paths.collection_dir("personal") / "agent.md").write_text("one\ntwo\n", encoding="utf-8")
    client.portal.call(sweep_once, get_knowledge_service(), _no_refresh)  # type: ignore[union-attr]
    # … then a person's upload.
    _submit(client, collection="shopee", title="Cache", description="d", body="first")

    changes = client.get("/api/v1/knowledge/changes").json()["changes"]
    edits = [c for c in changes if c["documents"]]
    by_collection = {c["collections"][0]: c for c in edits}
    assert by_collection["personal"]["writer"] == "disk"
    assert by_collection["shopee"]["writer"] == "user"
    assert [d["path"] for d in by_collection["personal"]["documents"]] == ["personal/agent.md"]
    assert by_collection["personal"]["documents"][0]["added"] == 2
    assert by_collection["shopee"]["documents"][0]["added"] > 0
    times = [c["time"] for c in changes]
    assert times == sorted(times, reverse=True)

    only = client.get("/api/v1/knowledge/changes", params={"collection": "personal"}).json()
    assert {c["collections"][0] for c in only["changes"] if c["collections"]} == {"personal"}


def test_the_feed_filters_to_one_collection(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _create_collection(client, "personal")
    _submit(client, collection="personal", title="Mine", description="d", body="b")
    _submit(client, collection="shopee", title="Other", description="d", body="b")

    shopee = client.get("/api/v1/knowledge/changes", params={"collection": "shopee"}).json()
    assert all(c["collections"] == ["shopee"] for c in shopee["changes"])
    personal = client.get("/api/v1/knowledge/changes", params={"collection": "personal"}).json()
    assert personal["changes"][0]["documents"][0]["path"] == "personal/mine.md"


def test_there_is_no_route_for_a_documents_versions(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    doc = _submit(client, collection="shopee", title="Cache", description="d", body="first")
    for route in ("history", "history/diff", "history/version"):
        got = client.get(f"/api/v1/knowledge/{route}", params={"path": doc, "version": "0" * 40})
        assert got.status_code in (404, 405), route
    assert client.post("/api/v1/knowledge/history/restore", json={}).status_code in (404, 405)
