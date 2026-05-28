"""HTTP coverage for /api/v1/agents/{name}/config-files and /mcp-install."""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-cfg"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    # Deterministic shim resolution for the MCP-install endpoint.
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    return create_app(), shim


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register_claude(c: TestClient, tmp_path: pathlib.Path) -> None:
    # config_dir defaults to <HOME>/.claude (HOME is monkeypatched to tmp_path).
    # Registration requires that config dir to already exist (it auto-creates
    # only the skills/ leaf), so create it up front.
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = c.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "cc"},
    )
    assert r.status_code == 201, r.text


def test_list_and_read_config_file(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59700)
    with _client(app) as c:
        _register_claude(c, tmp_path)

        r = c.get("/api/v1/agents/cc/config-files")
        assert r.status_code == 200, r.text
        keys = [i["key"] for i in r.json()["items"]]
        assert keys == ["settings", "settings_local", "global", "memory"]

        # Read a not-yet-created file -> empty + exists false.
        r = c.get("/api/v1/agents/cc/config-files/settings")
        assert r.status_code == 200
        assert r.json() == {"key": "settings", "format": "json", "exists": False, "content": ""}

        # Read an existing file -> current content, exists true.
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
        r = c.get("/api/v1/agents/cc/config-files/settings")
        assert r.status_code == 200
        assert r.json()["exists"] is True
        assert r.json()["content"] == '{"theme": "dark"}'


@pytest.mark.acceptance(spec="004-agent-registry", scenario="save a config file with valid content")
def test_write_config_file_valid(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59710)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        (tmp_path / ".claude").mkdir(exist_ok=True)
        settings = tmp_path / ".claude" / "settings.json"
        settings.write_text('{"theme": "light"}', encoding="utf-8")

        r = c.put("/api/v1/agents/cc/config-files/settings", json={"content": '{"theme": "dark"}'})
        assert r.status_code == 200, r.text
        assert r.json()["key"] == "settings"
        assert r.json()["exists"] is True
        # Atomic write landed and a .bak preserves the prior content.
        assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}'
        assert (tmp_path / ".claude" / "settings.json.bak").read_text(
            encoding="utf-8"
        ) == '{"theme": "light"}'
        # Read-back through the API agrees.
        r = c.get("/api/v1/agents/cc/config-files/settings")
        assert r.json()["content"] == '{"theme": "dark"}'


@pytest.mark.acceptance(spec="004-agent-registry", scenario="reject malformed config-file content")
def test_write_config_file_malformed_422_file_unchanged(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59712)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        (tmp_path / ".claude").mkdir(exist_ok=True)
        settings = tmp_path / ".claude" / "settings.json"
        settings.write_text('{"theme": "light"}', encoding="utf-8")

        r = c.put("/api/v1/agents/cc/config-files/settings", json={"content": "{not json"})
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "CONFIG_FILE_FORMAT_INVALID"
        # File untouched, no .bak written.
        assert settings.read_text(encoding="utf-8") == '{"theme": "light"}'
        assert not (tmp_path / ".claude" / "settings.json.bak").exists()


def test_write_config_file_unknown_key_404(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59714)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        r = c.put("/api/v1/agents/cc/config-files/nope", json={"content": "x"})
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CONFIG_FILE_NOT_ALLOWED"


def test_unknown_key_404(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59720)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        r = c.get("/api/v1/agents/cc/config-files/nope")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CONFIG_FILE_NOT_ALLOWED"


def test_config_routes_unknown_agent_404(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59730)
    with _client(app) as c:
        r = c.get("/api/v1/agents/ghost/config-files")
        assert r.status_code == 404


def test_mcp_install_lifecycle(tmp_path, monkeypatch):
    app, shim = _app(tmp_path, monkeypatch, 59740)
    with _client(app) as c:
        _register_claude(c, tmp_path)

        r = c.get("/api/v1/agents/cc/mcp-install")
        assert r.status_code == 200
        assert r.json()["installed"] is False

        r = c.post("/api/v1/agents/cc/mcp-install")
        assert r.status_code == 200, r.text
        assert r.json()["installed"] is True
        assert r.json()["command"] == str(shim)
        data = json.loads((tmp_path / ".claude.json").read_text())
        assert data["mcpServers"]["coffer"] == {"command": str(shim)}

        r = c.get("/api/v1/agents/cc/mcp-install")
        assert r.json()["installed"] is True

        r = c.request("DELETE", "/api/v1/agents/cc/mcp-install")
        assert r.status_code == 200
        assert r.json()["installed"] is False
        data = json.loads((tmp_path / ".claude.json").read_text())
        assert "coffer" not in data.get("mcpServers", {})
