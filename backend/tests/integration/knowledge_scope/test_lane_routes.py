"""Integration: the Slice-7 lane routes over the real app — reads + deletes.

``GET .../handoff`` / ``.../consolidation-log`` mirror
``get_rules``: ``ensure_scope`` for the global name, read-only, 200 with an
empty list / null text for an empty store (never 404). The ``DELETE`` routes
mirror ``forget_fact``: 204 on success, 404 when the lane file is missing; each
appends one changelog line (except the changelog's own delete, which does not
self-append).
"""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.testclient import TestClient

from coffer.infrastructure.knowledge.paths import (
    consolidation_log_path,
    handoff_path,
    rules_path,
)
from coffer.infrastructure.knowledge_scope.handoff_files import write_handoff
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "lane-route-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _provision(c: TestClient) -> None:
    set_active_token(_TOKEN)
    r = c.get("/api/v1/knowledge", headers=_HEADERS)
    assert r.status_code == 200, r.text


# --- handoff ----------------------------------------------------------------


def test_handoff_route_lists_scenes(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59940)
    store_dir = tmp_path / "knowledge" / "global"
    with TestClient(app) as c:
        _provision(c)
        write_handoff(
            handoff_path(store_dir, "main"),
            branch="main",
            body="clean tree",
            updated_at=datetime(2026, 6, 21, 9, 0, tzinfo=UTC),
        )
        r = c.get("/api/v1/knowledge/global/handoff", headers=_HEADERS)
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
        r = c.get("/api/v1/knowledge/global/handoff", headers=_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json() == {"scenes": []}


# --- consolidation log ------------------------------------------------------


def test_consolidation_log_route_present(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59960)
    store_dir = tmp_path / "knowledge" / "global"
    with TestClient(app) as c:
        _provision(c)
        store_dir.mkdir(parents=True, exist_ok=True)
        consolidation_log_path(store_dir).write_text(
            "# log\n\n- drained 3 items\n", encoding="utf-8"
        )
        r = c.get("/api/v1/knowledge/global/consolidation-log", headers=_HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "drained 3 items" in data["text"]
        assert data["path"].endswith("consolidation-log.md")
        assert data["folder_path"].endswith("global")


def test_consolidation_log_route_absent(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59970)
    with TestClient(app) as c:
        _provision(c)
        r = c.get("/api/v1/knowledge/global/consolidation-log", headers=_HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["text"] is None
        assert data["path"].endswith("consolidation-log.md")


# --- lane deletes -----------------------------------------------------------


def test_delete_handoff_branch_removes_file_and_logs(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59990)
    store_dir = tmp_path / "knowledge" / "global"
    with TestClient(app) as c:
        _provision(c)
        scene = handoff_path(store_dir, "main")
        write_handoff(scene, branch="main", body="x", updated_at=datetime(2026, 6, 1, tzinfo=UTC))
        r = c.delete("/api/v1/knowledge/global/handoff/main", headers=_HEADERS)
        assert r.status_code == 204, r.text
        assert not scene.exists()
        log = consolidation_log_path(store_dir).read_text(encoding="utf-8")
        assert "deleted handoff/main" in log
        r2 = c.delete("/api/v1/knowledge/global/handoff/main", headers=_HEADERS)
        assert r2.status_code == 404, r2.text


def test_delete_rules_removes_lane_and_logs(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 60000)
    store_dir = tmp_path / "knowledge" / "global"
    with TestClient(app) as c:
        _provision(c)
        rf = rules_path(store_dir)
        rf.parent.mkdir(parents=True, exist_ok=True)
        rf.write_text("# Rules\n\n- always test\n", encoding="utf-8")
        r = c.delete("/api/v1/knowledge/global/rules", headers=_HEADERS)
        assert r.status_code == 204, r.text
        assert not rf.exists()
        log = consolidation_log_path(store_dir).read_text(encoding="utf-8")
        assert "deleted rules" in log
        r2 = c.delete("/api/v1/knowledge/global/rules", headers=_HEADERS)
        assert r2.status_code == 404, r2.text


def test_delete_consolidation_log_removes_file_without_self_append(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 60010)
    store_dir = tmp_path / "knowledge" / "global"
    with TestClient(app) as c:
        _provision(c)
        store_dir.mkdir(parents=True, exist_ok=True)
        clog = consolidation_log_path(store_dir)
        clog.write_text("# log\n\n- prior entry\n", encoding="utf-8")
        r = c.delete("/api/v1/knowledge/global/consolidation-log", headers=_HEADERS)
        assert r.status_code == 204, r.text
        # The changelog is gone and was NOT recreated by a self-append.
        assert not clog.exists()
        r2 = c.delete("/api/v1/knowledge/global/consolidation-log", headers=_HEADERS)
        assert r2.status_code == 404, r2.text
