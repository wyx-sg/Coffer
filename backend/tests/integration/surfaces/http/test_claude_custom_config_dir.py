"""Where a ``claude_code`` agent's ``.claude.json`` lives, over the real app.

Claude Code keeps ``.claude.json`` at ``$HOME/.claude.json`` when
``CLAUDE_CONFIG_DIR`` is unset (config dir ``~/.claude``) and at
``$CLAUDE_CONFIG_DIR/.claude.json`` when it is set. Probed against Claude Code
2.1.281 with a throwaway ``HOME``:

* ``HOME=$T/home CLAUDE_CONFIG_DIR=$T/cfg claude mcp add probe -s user -- /bin/echo hi``
  wrote ``$T/cfg/.claude.json`` ("File modified: …/cfg/.claude.json"); nothing
  was created under ``$T/home``.
* With ``$T/home/.claude.json`` carrying a ``homeonly`` server, ``claude mcp get
  homeonly`` under the same env answered "No MCP server named "homeonly".
  Configured servers: probe" — the home file is not read at all.
* With ``CLAUDE_CONFIG_DIR`` unset, the same ``mcp add`` wrote ``$HOME/.claude.json``.

So every surface that touches the ``global`` key — the config-file editor, the
MCP install target and the MCP-entry listing — has to resolve it per agent
(spec agent-registry/claude-code "Allowlist exactly the files Claude Code reads").
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-claude-custom-config-dir"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    return create_app(), shim


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _write_mcp(path: pathlib.Path, name: str) -> None:
    path.write_text(json.dumps({"mcpServers": {name: {"command": f"{name}-cmd"}}}))


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="resolve .claude.json inside a custom config directory",
)
def test_custom_config_dir_agent_uses_its_own_claude_json(tmp_path, monkeypatch):
    app, shim = _app(tmp_path, monkeypatch, 61900)
    custom = tmp_path / "work-claude"
    custom.mkdir()
    home_json = tmp_path / ".claude.json"
    inner_json = custom / ".claude.json"
    # The default install's file must be neither read nor written for this agent.
    _write_mcp(home_json, "home-only")
    _write_mcp(inner_json, "custom-only")
    home_before = home_json.read_bytes()

    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "work", "config_dir": str(custom)},
        )
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]

        # Config-file editor lists the file inside the config dir.
        r = c.get(f"/api/v1/agents/{uid}/config-files")
        assert r.status_code == 200, r.text
        items = {i["key"]: i for i in r.json()["items"]}
        assert items["global"]["path"] == str(inner_json)
        assert items["global"]["folder_path"] == str(custom)
        assert items["global"]["exists"] is True

        # MCP entries are read from it.
        r = c.get(f"/api/v1/agents/{uid}/mcp-entries")
        assert r.status_code == 200, r.text
        pairs = sorted((e["name"], e["source"]) for e in r.json()["items"])
        assert pairs == [("custom-only", "global")]

        # Install writes Coffer's entry into it.
        r = c.post(f"/api/v1/agents/{uid}/mcp-install")
        assert r.status_code == 200, r.text
        assert r.json()["installed"] is True

    data = json.loads(inner_json.read_text())
    assert data["mcpServers"]["coffer"] == {
        "command": str(shim),
        "args": ["--agent-uid", uid],
    }
    assert data["mcpServers"]["custom-only"] == {"command": "custom-only-cmd"}
    assert home_json.read_bytes() == home_before


def test_default_config_dir_agent_uses_home_claude_json(tmp_path, monkeypatch):
    app, shim = _app(tmp_path, monkeypatch, 61910)
    (tmp_path / ".claude").mkdir()
    home_json = tmp_path / ".claude.json"
    stray = tmp_path / ".claude" / ".claude.json"
    _write_mcp(home_json, "home-only")
    _write_mcp(stray, "stray")
    stray_before = stray.read_bytes()

    with _client(app) as c:
        r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]

        r = c.get(f"/api/v1/agents/{uid}/config-files")
        items = {i["key"]: i for i in r.json()["items"]}
        assert items["global"]["path"] == str(home_json)

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries")
        assert sorted(e["name"] for e in r.json()["items"]) == ["home-only"]

        r = c.post(f"/api/v1/agents/{uid}/mcp-install")
        assert r.status_code == 200, r.text

    assert json.loads(home_json.read_text())["mcpServers"]["coffer"]["command"] == str(shim)
    assert stray.read_bytes() == stray_before
