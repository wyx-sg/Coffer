"""``/api/v1/knowledge`` history and the stale-save refusal, observed through the
routes (spec knowledge "Keep every document's history",
"Save a document edited in the web UI").

``client`` (from ``conftest.py``) boots the full app with the knowledge root
under ``tmp_path``; the history is real git under it.
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.sweep import sweep_once
from coffer.infrastructure.knowledge import fs, paths

from .conftest import _create_collection, _submit


def test_a_documents_history_diff_and_restore_through_the_routes(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    doc = _submit(client, collection="shopee", title="Cache", description="d", body="first")
    read = client.get("/api/v1/knowledge/file", params={"path": doc}).json()
    saved = client.put(
        "/api/v1/knowledge/file",
        json={"path": doc, "body": "second", "expected_fingerprint": read["fingerprint"]},
    )
    assert saved.status_code == 200, saved.text

    history = client.get("/api/v1/knowledge/history", params={"path": doc})
    assert history.status_code == 200, history.text
    versions = history.json()["versions"]
    assert [(v["change"]["writer"], v["change"]["operation"]) for v in versions] == [
        ("user", "save"),
        ("user", "promote"),
    ]
    newest = versions[0]["change"]["version"]
    diff = client.get("/api/v1/knowledge/history/diff", params={"path": doc, "version": newest})
    assert diff.status_code == 200, diff.text
    assert "-first" in diff.json()["diff"] and "+second" in diff.json()["diff"]

    oldest = versions[-1]["change"]["version"]
    restored = client.post(
        "/api/v1/knowledge/history/restore", json={"path": doc, "version": oldest}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["body"].strip() == "first"

    unknown = client.get(
        "/api/v1/knowledge/history/diff", params={"path": doc, "version": "0" * 40}
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "KNOWLEDGE_VERSION_NOT_FOUND"


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
    _submit(client, collection="shopee", title="Cache", description="d", body="first")
    # An agent's edit on disk, in another collection, found by the sweep.
    (paths.collection_dir("personal") / "agent.md").write_text("one\ntwo\n", encoding="utf-8")
    client.portal.call(sweep_once, get_knowledge_service(), _no_refresh)  # type: ignore[union-attr]

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

    version = by_collection["personal"]["version"]
    diff = client.get(
        "/api/v1/knowledge/history/diff", params={"path": "personal/agent.md", "version": version}
    )
    assert diff.status_code == 200, diff.text
    assert "+one" in diff.json()["diff"]


def test_the_feed_filters_to_one_collection(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _create_collection(client, "personal")
    _submit(client, collection="personal", title="Mine", description="d", body="b")
    _submit(client, collection="shopee", title="Other", description="d", body="b")

    shopee = client.get("/api/v1/knowledge/changes", params={"collection": "shopee"}).json()
    assert all(c["collections"] == ["shopee"] for c in shopee["changes"])
    personal = client.get("/api/v1/knowledge/changes", params={"collection": "personal"}).json()
    assert personal["changes"][0]["documents"][0]["path"] == "personal/mine.md"


@pytest.mark.acceptance(spec="knowledge", scenario="a stale save answers with what is on disk now")
def test_a_stale_save_carries_the_document_as_it_is_on_disk(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    doc = _submit(client, collection="shopee", title="Cache", description="d", body="loaded")
    loaded = client.get("/api/v1/knowledge/file", params={"path": doc}).json()
    # Another writer rewrites it on disk while the editor has the old text open.
    fs.write_file(
        directory="shopee",
        title="Cache",
        description="d",
        body="rewritten elsewhere",
        relpath=doc,
    )

    stale = client.put(
        "/api/v1/knowledge/file",
        json={
            "path": doc,
            "body": "the user's text",
            "expected_fingerprint": loaded["fingerprint"],
        },
    )

    assert stale.status_code == 409, stale.text
    error = stale.json()["error"]
    assert error["code"] == "KNOWLEDGE_FILE_CONFLICT"
    now = client.get("/api/v1/knowledge/file", params={"path": doc}).json()
    assert error["details"]["saved"] is False
    assert error["details"]["current_body"].strip() == "rewritten elsewhere"
    assert error["details"]["current_fingerprint"] == now["fingerprint"]
    assert now["body"].strip() == "rewritten elsewhere"
    # The user's text goes in only with the new fingerprint.
    retry = client.put(
        "/api/v1/knowledge/file",
        json={"path": doc, "body": "the user's text", "expected_fingerprint": now["fingerprint"]},
    )
    assert retry.status_code == 200, retry.text
