"""HTTP coverage for /api/v1/agents/{name}/native-memory (spec 004).

Boots the real app, registers a claude_code agent whose config_dir is a temp
tree carrying a ``projects/<slug>/memory`` store, and asserts the listing.
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-native-mem"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register_claude(c: TestClient, config_dir: pathlib.Path) -> None:
    # Registration requires the config dir to already exist.
    config_dir.mkdir(parents=True, exist_ok=True)
    r = c.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "cc", "config_dir": str(config_dir)},
    )
    assert r.status_code == 201, r.text


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="the native memory scan lists an agent's own per-project stores",
)
def test_list_native_memory_returns_store(tmp_path, monkeypatch):
    config_dir = tmp_path / "cc-config"
    mem = config_dir / "projects" / "-X" / "memory"
    mem.mkdir(parents=True)
    (mem / "a.md").write_text("x", encoding="utf-8")
    (mem / "MEMORY.md").write_text("index", encoding="utf-8")

    app = _app(tmp_path, monkeypatch, 59800)
    with _client(app) as c:
        _register_claude(c, config_dir)

        r = c.get("/api/v1/agents/cc/native-memory")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["project"] == "X"
        assert item["path"] == "/X"
        assert item["memory_dir"] == str(mem)
        # MEMORY.md is excluded from the count.
        assert item["item_count"] == 1


def test_list_native_memory_empty_when_no_projects_dir(tmp_path, monkeypatch):
    config_dir = tmp_path / "cc-config"
    app = _app(tmp_path, monkeypatch, 59810)
    with _client(app) as c:
        _register_claude(c, config_dir)
        r = c.get("/api/v1/agents/cc/native-memory")
        assert r.status_code == 200, r.text
        assert r.json()["items"] == []


def test_list_native_memory_unknown_agent_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59820)
    with _client(app) as c:
        r = c.get("/api/v1/agents/ghost/native-memory")
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
