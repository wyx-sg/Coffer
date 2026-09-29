"""``/api/v1/knowledge`` history, the stale-save refusal, and Curate now's
progress, observed through the routes (spec knowledge "Keep every document's
history and undo a pass as a whole", "Save a document edited in the web UI",
"Run curation on a sweep and on demand").

``client`` (from ``conftest.py``) boots the full app with the knowledge root
under ``tmp_path``; the history is real git under it.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.infrastructure.knowledge import fs, inbox
from coffer.surfaces.http.event_dependencies import get_event_broker
from coffer.surfaces.http.knowledge import curation_state

from .conftest import _create_collection, _hold_material, _submit


def _uid(client, name: str) -> str:  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/resources", params={"kind": "knowledge", "name": name})
    return str(r.json()["resources"][0]["uid"])


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


def test_only_a_curation_pass_can_be_undone(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    _submit(client, collection="shopee", title="Cache", description="d", body="first")
    feed = client.get("/api/v1/knowledge/changes").json()
    promote = next(c for c in feed["changes"] if c["operation"] == "promote")

    refused = client.post(f"/api/v1/knowledge/changes/{promote['version']}/undo")
    assert refused.status_code == 400, refused.text
    assert refused.json()["error"]["code"] == "KNOWLEDGE_NOT_A_PASS"

    detail = client.get(f"/api/v1/knowledge/changes/{promote['version']}")
    assert detail.status_code == 200, detail.text
    assert [d["path"] for d in detail.json()["diffs"]] == ["shopee/cache.md"]


def test_the_feed_filters_to_one_collection_and_lists_waiting_items(  # type: ignore[no-untyped-def]
    client, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    _create_collection(client, "personal")
    _submit(client, collection="personal", title="Mine", description="d", body="b")
    _hold_material(monkeypatch)
    client.post(
        "/api/v1/knowledge/material",
        json={"collection": "shopee", "title": "Waiting", "description": "d", "body": "b"},
        headers={"X-Coffer-Actor": "user"},
    )

    shopee = client.get("/api/v1/knowledge/changes", params={"collection": "shopee"}).json()
    assert [w["title"] for w in shopee["waiting"]] == ["Waiting"]
    assert all(c["collections"] == ["shopee"] for c in shopee["changes"])
    personal = client.get("/api/v1/knowledge/changes", params={"collection": "personal"}).json()
    assert personal["waiting"] == []
    assert personal["changes"][0]["documents"][0]["path"] == "personal/mine.md"


@pytest.mark.acceptance(spec="knowledge", scenario="a stale save answers with what is on disk now")
def test_a_stale_save_carries_the_document_as_it_is_on_disk(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    doc = _submit(client, collection="shopee", title="Cache", description="d", body="loaded")
    loaded = client.get("/api/v1/knowledge/file", params={"path": doc}).json()
    # Curation rewrites it on disk while the editor has the old text open.
    fs.write_file(
        directory="shopee",
        title="Cache",
        description="d",
        body="rewritten by curation",
        relpath=doc,
        curated=True,
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
    assert error["details"]["current_body"].strip() == "rewritten by curation"
    assert error["details"]["current_fingerprint"] == now["fingerprint"]
    assert now["body"].strip() == "rewritten by curation"
    # The user's text goes in only with the new fingerprint.
    retry = client.put(
        "/api/v1/knowledge/file",
        json={"path": doc, "body": "the user's text", "expected_fingerprint": now["fingerprint"]},
    )
    assert retry.status_code == 200, retry.text


class _SettlingPass:
    """A pass that settles its item and notes the progress the daemon reports
    while it runs — the in-flight list is what a page polls."""

    def __init__(self, uid: str) -> None:
        self.uid = uid
        self.seen: list[tuple[int | None, int | None]] = []

    async def __call__(self, service: Any, uid: str, *, item: Any, actor: str) -> dict:
        run = UPKEEP_RUNS.running("knowledge", self.uid)
        self.seen.append((run.done, run.total) if run else (None, None))
        inbox.discard_material("shopee", item.material)
        return {"status": "ok", "collection": "shopee", "item": item.material}


@pytest.mark.acceptance(spec="knowledge", scenario="curate now reports progress")
def test_curate_now_reports_progress_on_the_in_flight_list_and_the_stream(  # type: ignore[no-untyped-def]
    client, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    _hold_material(monkeypatch)
    for title in ("One", "Two", "Three"):
        client.post(
            "/api/v1/knowledge/material",
            json={"collection": "shopee", "title": title, "description": "d", "body": "b"},
        )
    uid = _uid(client, "shopee")
    fake = _SettlingPass(uid)
    monkeypatch.setattr(curation_state, "_curation_runner", fake)
    stream = get_event_broker().subscribe()

    resp = client.post(f"/api/v1/knowledge/collections/{uid}/curate")

    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert (run["status"], run["total"], len(run["passes"])) == ("ok", 3, 3)
    # While pass k ran, the in-flight list read k-1 of 3.
    assert fake.seen == [(0, 3), (1, 3), (2, 3)]
    announced = [e for e in _drain(stream) if e.kind == "knowledge" and e.id == uid]
    assert len(announced) == 4  # the start, and each of the three passes
    stream.close()
    # The run is over, so the in-flight list no longer names it.
    assert client.get("/api/v1/upkeep/runs").json()["runs"] == []


def _drain(stream: Any) -> list[Any]:
    items = []
    while stream.pending():
        items.append(stream._items.popleft())
    return items
