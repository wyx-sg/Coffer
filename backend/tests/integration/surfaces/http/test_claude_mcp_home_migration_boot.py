"""The daemon's startup moves a pre-upgrade Claude Code MCP entry, over the real app.

An agent registered with a custom config directory had its ``coffer`` entry
written to ``$HOME/.claude.json`` by an older Coffer. The next daemon start
moves it into ``<config_dir>/.claude.json`` — the file Claude Code actually
reads for that agent — and the agent reports "installed" (spec
agent-registry/claude-code
"Install Coffer's MCP entry into Claude Code's .claude.json").
"""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-claude-mcp-home-migration"


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="an entry installed before the config dir was honoured moves to the agent's own file",
)
def test_restart_moves_the_home_entry_into_the_custom_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "61930")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "61939")
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    custom = tmp_path / "work-claude"
    custom.mkdir()
    home_json = tmp_path / ".claude.json"
    set_active_token(TOKEN)

    with TestClient(create_app(), headers={"X-Coffer-Token": TOKEN}) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "work", "config_dir": str(custom)},
        )
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]

    # What the pre-upgrade install left behind.
    entry = {"command": str(shim), "args": ["--agent-uid", uid]}
    home_json.write_text(json.dumps({"mcpServers": {"coffer": entry}}), encoding="utf-8")

    set_active_token(TOKEN)
    with TestClient(create_app(), headers={"X-Coffer-Token": TOKEN}) as c:
        r = c.get(f"/api/v1/agents/{uid}/mcp-install")
        assert r.status_code == 200, r.text
        assert r.json()["installed"] is True

    assert json.loads((custom / ".claude.json").read_text()) == {"mcpServers": {"coffer": entry}}
    assert json.loads(home_json.read_text()) == {"mcpServers": {}}
