"""The memory sync through the daemon: its routes, its audit log and its
database (spec memory "Audit every sync, undo and curation request", "Add no
table or resource kind", "Sync on an interval and on demand").

Boots the real app against a fresh SQLite file with ``HOME`` pinned into
``tmp_path``. The sync worker is on by default; its first sync on a machine
only stages a preview, so what a test asks for is what gets written.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.integration.memory._sync_harness import cc_file, cc_project, codex_dir, codex_memory
from tests.integration.memory.conftest import init_repository

_TOKEN = "test-token-memory-sync"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59340")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59349")
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def client(home: pathlib.Path):  # type: ignore[no-untyped-def]
    app = create_app()
    set_active_token(_TOKEN)
    with TestClient(
        app, base_url="http://localhost", headers=_HEADERS, raise_server_exceptions=False
    ) as c:
        yield c


def _seed(c: TestClient, home: pathlib.Path) -> pathlib.Path:
    for agent_type, name in (("claude_code", "cc"), ("codex", "codex")):
        r = c.post("/api/v1/agents", json={"type": agent_type, "name": name})
        assert r.status_code == 201, r.text
    repo = init_repository(home / "src" / "payments", remote="git@github.com:acme/payments.git")
    cc_project(home / ".claude", repo, {"p.md": cc_file("Ledger", "Retries", "project", "Retry.")})
    codex_dir(home / ".codex", codex_memory([("Payments", str(repo), ["Codex lesson one here."])]))
    return repo


@pytest.mark.acceptance(spec="memory", scenario="audit a requested sync with its actor")
def test_a_requested_sync_records_one_event_naming_the_user(
    client: TestClient, home: pathlib.Path
) -> None:
    _seed(client, home)
    r = client.post("/api/v1/memory/sync/run", headers={**_HEADERS, "X-Coffer-Actor": "alice"})
    assert r.status_code == 200, r.text
    assert len(r.json()["details"]["hub"]["created"]) == 2

    state = client.get("/api/v1/memory/sync/state").json()
    assert state["preview"]["copies"] == 2
    assert {p["key"] for p in state["projects"]} == {"github.com/acme/payments"}
    r = client.post("/api/v1/memory/sync/preview/write")
    assert r.status_code == 200, r.text

    entries = client.get("/api/v1/audit", params={"event_type": "memory_synced"}).json()["entries"]
    assert sorted(e["actor"] for e in entries) == ["alice", "user"]

    listed = client.get(
        "/api/v1/memory/sync/entries", params={"project": "github.com/acme/payments"}
    ).json()["entries"]
    by_agent = {e["origin_agent"]: e["copies"] for e in listed}
    assert by_agent["codex"] == {"claude_code": "written", "codex": "origin"}
    assert by_agent["claude_code"] == {"claude_code": "origin", "codex": "written"}


def test_cancel_with_no_preview_is_a_conflict(client: TestClient, home: pathlib.Path) -> None:
    r = client.post("/api/v1/memory/sync/preview/cancel")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "MEMORY_SYNC_NO_PREVIEW"


@pytest.mark.acceptance(spec="memory", scenario="keep the hub and the ledger as files only")
def test_keep_the_hub_and_the_ledger_as_files_only(client: TestClient, home: pathlib.Path) -> None:
    _seed(client, home)
    assert client.post("/api/v1/memory/sync/run").status_code == 200
    assert client.post("/api/v1/memory/sync/preview/write").status_code == 200

    with sqlite3.connect(home / "c.db") as db:
        tables = [row[0] for row in db.execute("select name from sqlite_master where type='table'")]
    assert not [t for t in tables if "memory" in t and "sync" in t]
    assert (home / ".coffer" / "local" / "memory-sync.json").is_file()
    assert list((home / ".coffer" / "vault" / "memory").rglob("*.md"))


def test_memory_sync_is_on_by_default(client: TestClient) -> None:
    cfg = client.get("/api/v1/internal-engine-config").json()
    assert cfg["upkeep"]["memory_sync"]["enabled"] is True
    assert cfg["upkeep"]["memory_sync"]["default_interval_s"] == 3600
