"""Integration: the three Slice-7 lane read routes over the real app.

``GET .../journal`` / ``.../handoff`` / ``.../consolidation-log`` mirror
``get_rules``: ``ensure_store`` for the global name, read-only, 200 with an
empty list / null text for an empty store (never 404).
"""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.testclient import TestClient

from coffer.infrastructure.knowledge.paths import (
    consolidation_log_path,
    handoff_path,
    journal_path,
)
from coffer.infrastructure.memory.handoff_files import write_handoff
from coffer.infrastructure.memory.journal_files import append_entry
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "lane-route-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _provision(c: TestClient) -> None:
    set_active_token(_TOKEN)
    r = c.get("/api/v1/memory_stores", headers=_HEADERS)
    assert r.status_code == 200, r.text


# --- journal ----------------------------------------------------------------


def test_journal_route_lists_newest_first(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59920)
    store_dir = tmp_path / "memory" / "global"
    with TestClient(app) as c:
        _provision(c)
        append_entry(
            journal_path(store_dir, "2026-05"),
            timestamp=datetime(2026, 5, 1, tzinfo=UTC),
            body="May",
        )
        append_entry(
            journal_path(store_dir, "2026-06"),
            timestamp=datetime(2026, 6, 1, tzinfo=UTC),
            body="June",
        )
        r = c.get("/api/v1/memory_stores/global/journal", headers=_HEADERS)
        assert r.status_code == 200, r.text
        files = r.json()["files"]
        assert [f["period"] for f in files] == ["2026-06", "2026-05"]
        assert "June" in files[0]["text"]
        assert files[0]["path"].endswith("journal/2026-06.md")
        assert files[0]["folder_path"].endswith("journal")


def test_journal_route_empty_store(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59930)
    with TestClient(app) as c:
        _provision(c)
        r = c.get("/api/v1/memory_stores/global/journal", headers=_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json() == {"files": []}


# --- handoff ----------------------------------------------------------------


def test_handoff_route_lists_scenes(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59940)
    store_dir = tmp_path / "memory" / "global"
    with TestClient(app) as c:
        _provision(c)
        write_handoff(
            handoff_path(store_dir, "main"),
            branch="main",
            body="clean tree",
            updated_at=datetime(2026, 6, 21, 9, 0, tzinfo=UTC),
        )
        r = c.get("/api/v1/memory_stores/global/handoff", headers=_HEADERS)
        assert r.status_code == 200, r.text
        scenes = r.json()["scenes"]
        assert len(scenes) == 1
        assert scenes[0]["branch"] == "main"
        assert scenes[0]["text"] == "clean tree"
        assert scenes[0]["updated_at"].startswith("2026-06-21T09:00:00")
        assert scenes[0]["path"].endswith("handoff/main.md")
        assert scenes[0]["folder_path"].endswith("handoff")


def test_handoff_route_empty_store(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59950)
    with TestClient(app) as c:
        _provision(c)
        r = c.get("/api/v1/memory_stores/global/handoff", headers=_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json() == {"scenes": []}


# --- consolidation log ------------------------------------------------------


def test_consolidation_log_route_present(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59960)
    store_dir = tmp_path / "memory" / "global"
    with TestClient(app) as c:
        _provision(c)
        store_dir.mkdir(parents=True, exist_ok=True)
        consolidation_log_path(store_dir).write_text(
            "# log\n\n- drained 3 items\n", encoding="utf-8"
        )
        r = c.get("/api/v1/memory_stores/global/consolidation-log", headers=_HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "drained 3 items" in data["text"]
        assert data["path"].endswith("consolidation-log.md")
        assert data["folder_path"].endswith("global")


def test_consolidation_log_route_absent(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59970)
    with TestClient(app) as c:
        _provision(c)
        r = c.get("/api/v1/memory_stores/global/consolidation-log", headers=_HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["text"] is None
        assert data["path"].endswith("consolidation-log.md")
