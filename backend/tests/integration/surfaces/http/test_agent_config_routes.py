"""HTTP coverage for /api/v1/agents/{name}/config-files and /mcp-install."""

from __future__ import annotations

import hashlib
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


@pytest.mark.acceptance(spec="004-agent-registry", scenario="list an agent's config files")
def test_list_and_read_config_file(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59700)
    with _client(app) as c:
        _register_claude(c, tmp_path)

        settings_path = tmp_path / ".claude" / "settings.json"
        claude_dir = tmp_path / ".claude"

        r = c.get("/api/v1/agents/cc/config-files")
        assert r.status_code == 200, r.text
        items = {i["key"]: i for i in r.json()["items"]}
        assert list(items) == ["settings", "settings_local", "global", "instructions", "subagents"]
        assert items["settings"]["kind"] == "file"
        assert items["settings"]["files"] is None
        assert items["subagents"]["kind"] == "directory"
        # The read-only viewer needs absolute paths for open/reveal/copy-path
        # (FR-038): a file entry exposes its own path + its containing folder.
        assert items["settings"]["path"] == str(settings_path)
        assert items["settings"]["folder_path"] == str(claude_dir)
        # A directory entry's path IS the folder; folder_path is its parent.
        assert items["subagents"]["path"] == str(claude_dir / "agents")
        assert items["subagents"]["folder_path"] == str(claude_dir)

        # Read a not-yet-created file -> empty + exists false, empty fingerprint.
        # path/folder_path are still resolved even when the file is absent.
        r = c.get("/api/v1/agents/cc/config-files/settings")
        assert r.status_code == 200
        assert r.json() == {
            "key": "settings",
            "path": str(settings_path),
            "folder_path": str(claude_dir),
            "format": "json",
            "exists": False,
            "content": "",
            "fingerprint": "",
            "memory_block": False,
        }

        # Read an existing file -> current content, exists true, sha256 fingerprint.
        claude_dir.mkdir(exist_ok=True)
        settings_path.write_text('{"theme": "dark"}', encoding="utf-8")
        r = c.get("/api/v1/agents/cc/config-files/settings")
        assert r.status_code == 200
        assert r.json()["exists"] is True
        assert r.json()["content"] == '{"theme": "dark"}'
        assert r.json()["fingerprint"] == hashlib.sha256(b'{"theme": "dark"}').hexdigest()
        assert r.json()["memory_block"] is False
        assert r.json()["path"] == str(settings_path)
        assert r.json()["folder_path"] == str(claude_dir)


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


def test_dir_entry_listing_and_child_round_trip(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59750)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"

        # Directory entry before the agents/ dir exists: exists=false, no files,
        # and listing does not create the directory.
        r = c.get("/api/v1/agents/cc/config-files")
        sub = next(i for i in r.json()["items"] if i["key"] == "subagents")
        assert sub["kind"] == "directory"
        assert sub["exists"] is False
        assert sub["files"] is None
        assert not agents_dir.exists()

        # PUT a child -> created on disk, refreshed listing returned.
        r = c.put(
            "/api/v1/agents/cc/config-files/subagents/files/reviewer.md",
            json={"content": "# Reviewer\n"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["kind"] == "directory"
        assert r.json()["exists"] is True
        assert [f["relpath"] for f in r.json()["files"]] == ["reviewer.md"]
        assert (agents_dir / "reviewer.md").read_text(encoding="utf-8") == "# Reviewer\n"

        # GET the child back.
        r = c.get("/api/v1/agents/cc/config-files/subagents/files/reviewer.md")
        assert r.status_code == 200
        assert r.json()["exists"] is True
        assert r.json()["content"] == "# Reviewer\n"
        assert r.json()["fingerprint"] == hashlib.sha256(b"# Reviewer\n").hexdigest()

        # Listing now shows the child too (nested files included).
        (agents_dir / "team").mkdir()
        (agents_dir / "team" / "helper.md").write_text("# Helper\n", encoding="utf-8")
        r = c.get("/api/v1/agents/cc/config-files")
        sub = next(i for i in r.json()["items"] if i["key"] == "subagents")
        assert [f["relpath"] for f in sub["files"]] == ["reviewer.md", "team/helper.md"]

        # DELETE -> 204, file removed with a .bak of the prior content.
        r = c.request("DELETE", "/api/v1/agents/cc/config-files/subagents/files/reviewer.md")
        assert r.status_code == 204, r.text
        assert not (agents_dir / "reviewer.md").exists()
        assert (agents_dir / "reviewer.md.bak").read_text(encoding="utf-8") == "# Reviewer\n"
        r = c.get("/api/v1/agents/cc/config-files")
        sub = next(i for i in r.json()["items"] if i["key"] == "subagents")
        assert [f["relpath"] for f in sub["files"]] == ["team/helper.md"]


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="reject directory file paths outside the entry"
)
def test_dir_child_path_escape_and_extension_rejected(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59760)
    with _client(app) as c:
        _register_claude(c, tmp_path)

        # Traversal (`../escape.md`, slash percent-encoded so the client does
        # not normalise it away) -> 404 CONFIG_FILE_NOT_ALLOWED on GET and PUT.
        r = c.get("/api/v1/agents/cc/config-files/subagents/files/..%2Fescape.md")
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "CONFIG_FILE_NOT_ALLOWED"
        r = c.put(
            "/api/v1/agents/cc/config-files/subagents/files/..%2Fescape.md",
            json={"content": "x"},
        )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "CONFIG_FILE_NOT_ALLOWED"
        assert not (tmp_path / ".claude" / "escape.md").exists()

        # Non-.md extension -> 422 CONFIG_FILE_FORMAT_INVALID on GET and PUT.
        r = c.get("/api/v1/agents/cc/config-files/subagents/files/note.txt")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "CONFIG_FILE_FORMAT_INVALID"
        r = c.put(
            "/api/v1/agents/cc/config-files/subagents/files/note.txt",
            json={"content": "x"},
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "CONFIG_FILE_FORMAT_INVALID"
        assert not (tmp_path / ".claude" / "agents" / "note.txt").exists()


@pytest.mark.acceptance(spec="004-agent-registry", scenario="reject stale config-file writes")
def test_stale_write_409_then_fresh_fingerprint_succeeds(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59770)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        settings.write_text('{"theme": "light"}', encoding="utf-8")

        # Read -> capture fingerprint.
        r = c.get("/api/v1/agents/cc/config-files/settings")
        stale_fp = r.json()["fingerprint"]

        # Another process changes the file on disk.
        settings.write_text('{"theme": "solar"}', encoding="utf-8")

        # Write-back with the stale fingerprint -> 409, file unchanged.
        r = c.put(
            "/api/v1/agents/cc/config-files/settings",
            json={"content": '{"theme": "dark"}', "expected_fingerprint": stale_fp},
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "CONFIG_FILE_STALE"
        assert settings.read_text(encoding="utf-8") == '{"theme": "solar"}'

        # Re-read -> fresh fingerprint allows the write.
        r = c.get("/api/v1/agents/cc/config-files/settings")
        fresh_fp = r.json()["fingerprint"]
        assert fresh_fp != stale_fp
        r = c.put(
            "/api/v1/agents/cc/config-files/settings",
            json={"content": '{"theme": "dark"}', "expected_fingerprint": fresh_fp},
        )
        assert r.status_code == 200, r.text
        assert settings.read_text(encoding="utf-8") == '{"theme": "dark"}'


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
