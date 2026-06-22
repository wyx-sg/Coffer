"""HTTP coverage for the Slice 6 agent session + hook + native-memory surface.

- GET  /api/v1/agents/{name}/session-context        → rules bundle
- POST /api/v1/agents/{name}/sessions/{sid}/end      → idempotent distill (no-op ok)
- GET/POST/DELETE /api/v1/agents/{name}/hook-install → hook status/install/uninstall
- PATCH /api/v1/agents/{name} {disable_native_memory} → field + on-disk transform
"""

from __future__ import annotations

import json
import pathlib

from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-sess"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    monkeypatch.setenv("COFFER_AUTO_DISTILL", "0")  # keep the sweep worker quiet
    hook = tmp_path / "coffer-hook"
    hook.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_HOOK_PATH", str(hook))
    return create_app(), hook


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register_claude(c: TestClient, tmp_path: pathlib.Path) -> None:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
    assert r.status_code == 201, r.text


def test_session_context_returns_seeded_bundle(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59810)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        r = c.get("/api/v1/agents/cc/session-context")
        assert r.status_code == 200, r.text
        ctx = r.json()["additional_context"]
        assert "coffer__resume" in ctx
        assert "coffer__remember" in ctx


def test_session_context_unknown_agent_404(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59811)
    with _client(app) as c:
        r = c.get("/api/v1/agents/nope/session-context")
        assert r.status_code == 404, r.text


def test_session_end_unknown_session_is_noop_200(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59812)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        r = c.post("/api/v1/agents/cc/sessions/no-such/end", json={"cwd": str(tmp_path)})
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] in {"not_found", "no_model", "skipped"}


def test_session_end_unknown_agent_404(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59813)
    with _client(app) as c:
        r = c.post("/api/v1/agents/nope/sessions/s1/end", json={})
        assert r.status_code == 404, r.text


def test_hook_install_lifecycle(tmp_path, monkeypatch):
    app, hook = _app(tmp_path, monkeypatch, 59814)
    with _client(app) as c:
        _register_claude(c, tmp_path)

        r = c.get("/api/v1/agents/cc/hook-install")
        assert r.status_code == 200, r.text
        assert r.json()["installed"] is False

        r = c.post("/api/v1/agents/cc/hook-install")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["installed"] is True
        assert str(hook) in body["command"]
        assert "--agent cc" in body["command"]

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert set(data["hooks"]) == {"SessionStart", "SessionEnd"}

        assert c.get("/api/v1/agents/cc/hook-install").json()["installed"] is True

        r = c.delete("/api/v1/agents/cc/hook-install")
        assert r.status_code == 200, r.text
        assert r.json()["installed"] is False
        assert c.get("/api/v1/agents/cc/hook-install").json()["installed"] is False


def test_patch_disable_native_memory_drives_settings(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59815)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        # default is OFF
        assert c.get("/api/v1/agents/cc").json()["disable_native_memory"] is False

        r = c.patch("/api/v1/agents/cc", json={"disable_native_memory": True})
        assert r.status_code == 200, r.text
        assert r.json()["disable_native_memory"] is True
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert data["autoMemoryEnabled"] is False

        # toggle back off restores
        r = c.patch("/api/v1/agents/cc", json={"disable_native_memory": False})
        assert r.json()["disable_native_memory"] is False
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "autoMemoryEnabled" not in data
