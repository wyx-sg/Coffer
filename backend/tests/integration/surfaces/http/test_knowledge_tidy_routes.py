"""A tidy as one change, undoing it, and a collection's contents, observed
through the routes (spec knowledge "Record a tidy as one change", "Undo a
tidy", "Show a collection's contents by page type").

``client`` (from ``conftest.py``) boots the full app with the knowledge root
under ``tmp_path``; the history is real git under it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from coffer.infrastructure.knowledge.history import KNOWLEDGE_HISTORY
from coffer.infrastructure.knowledge.paths import knowledge_root
from coffer.infrastructure.knowledge.tidy_runs import TIDY_RUNS
from coffer.infrastructure.vault.instance import vault_writer

from .conftest import _create_collection, _submit


@pytest.fixture(autouse=True)
def _no_open_tidy() -> Iterator[None]:
    TIDY_RUNS.clear()
    yield
    TIDY_RUNS.clear()


def _uid(client, name: str) -> str:  # type: ignore[no-untyped-def]
    rows = client.get("/api/v1/knowledge/collections").json()["collections"]
    return str(next(r["uid"] for r in rows if r["name"] == name))


def _feed(client, collection: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/knowledge/changes", params={"collection": collection})
    assert r.status_code == 200, r.text
    return list(r.json()["changes"])


def _write_page(collection: str, slug: str, body: str) -> str:
    path = knowledge_root() / collection / "pages" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {slug}\ntype: concept\n---\n\n{body}\n", encoding="utf-8")
    return f"{collection}/pages/{slug}.md"


@pytest.mark.acceptance(
    spec="knowledge", scenario="a tidy's edits land as one change with its report"
)
def test_a_tidys_edits_land_as_one_change_with_its_report(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    first = _write_page("shopee", "gateway", "Old text.")
    KNOWLEDGE_HISTORY.settle()
    uid = _uid(client, "shopee")

    started = client.post(f"/api/v1/knowledge/collections/{uid}/tidy/start")
    assert started.status_code == 200, started.text
    assert started.json()["running"] is True
    listed = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert listed[0]["tidy_running"] is True

    _write_page("shopee", "gateway", "New text.")
    second = _write_page("shopee", "cache", "A new page.")
    # Neither a vault-wide settle (the scanner, a sync round) nor a read commits
    # a paused collection's edits.
    vault_writer().settle()
    before = len(_feed(client, "shopee"))

    finished = client.post(
        f"/api/v1/knowledge/collections/{uid}/tidy/finish",
        json={"summary": "Merged two pages; nothing left to decide."},
    )
    assert finished.status_code == 200, finished.text
    change = finished.json()["change"]
    assert change["operation"] == "tidy"
    assert change["writer"] == "agent"
    assert change["status"] == "reported"
    assert change["summary"] == "Merged two pages; nothing left to decide."
    assert sorted(d["path"] for d in change["documents"]) == sorted([first, second])
    feed = _feed(client, "shopee")
    assert len(feed) == before + 1
    assert feed[0]["version"] == change["version"]
    listed = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert listed[0]["tidy_running"] is False


def test_finishing_a_tidy_that_changed_nothing_commits_nothing(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    uid = _uid(client, "shopee")
    client.post(f"/api/v1/knowledge/collections/{uid}/tidy/start")
    finished = client.post(f"/api/v1/knowledge/collections/{uid}/tidy/finish", json={})
    assert finished.status_code == 200, finished.text
    assert finished.json()["change"] is None


@pytest.mark.acceptance(spec="knowledge", scenario="undo a tidy")
def test_undo_puts_every_file_a_tidy_touched_back(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    kept = _write_page("shopee", "gateway", "Old text.")
    KNOWLEDGE_HISTORY.settle()
    uid = _uid(client, "shopee")
    client.post(f"/api/v1/knowledge/collections/{uid}/tidy/start")
    _write_page("shopee", "gateway", "New text.")
    added = _write_page("shopee", "cache", "A new page.")
    change = client.post(
        f"/api/v1/knowledge/collections/{uid}/tidy/finish", json={"summary": "Tidied."}
    ).json()["change"]

    undone = client.post(f"/api/v1/knowledge/changes/{change['version']}/undo", json={})
    assert undone.status_code == 200, undone.text
    assert undone.json()["operation"] == "restore"
    assert undone.json()["undoes"] == change["version"]
    assert "Old text." in (knowledge_root() / kept).read_text(encoding="utf-8")
    assert not (knowledge_root() / added).exists()


@pytest.mark.acceptance(
    spec="knowledge", scenario="undoing a tidy asks before discarding later edits"
)
def test_undo_names_files_edited_since_and_needs_force(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    page = _write_page("shopee", "gateway", "Old text.")
    KNOWLEDGE_HISTORY.settle()
    uid = _uid(client, "shopee")
    client.post(f"/api/v1/knowledge/collections/{uid}/tidy/start")
    _write_page("shopee", "gateway", "Tidied text.")
    change = client.post(
        f"/api/v1/knowledge/collections/{uid}/tidy/finish", json={"summary": "Tidied."}
    ).json()["change"]
    _write_page("shopee", "gateway", "Edited after the tidy.")

    refused = client.post(f"/api/v1/knowledge/changes/{change['version']}/undo", json={})
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "KNOWLEDGE_UNDO_CONFLICT"
    assert refused.json()["error"]["details"]["documents"] == [page]
    assert "Edited after the tidy." in (knowledge_root() / page).read_text(encoding="utf-8")

    forced = client.post(
        f"/api/v1/knowledge/changes/{change['version']}/undo", json={"force": True}
    )
    assert forced.status_code == 200, forced.text
    assert "Old text." in (knowledge_root() / page).read_text(encoding="utf-8")


@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection lists its pages and sources with their types"
)
def test_a_collection_lists_its_pages_and_sources_with_their_types(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    page = _write_page("shopee", "gateway", "Text.")
    source = _submit(client, collection="shopee", title="Notes", description="d", body="b")

    r = client.get(f"/api/v1/knowledge/collections/{_uid(client, 'shopee')}/files")
    assert r.status_code == 200, r.text
    by_path = {f["path"]: f for f in r.json()["files"]}
    assert by_path[page]["kind"] == "page" and by_path[page]["page_type"] == "concept"
    assert by_path[source]["kind"] == "source" and by_path[source]["waiting"] is True
