"""Acceptance coverage, over the real app, for the ``antigravity`` agent type
(spec agent-registry/antigravity).

Boots ``create_app`` against a temp ``HOME`` so ``~/.gemini/config`` is a temp
tree, registers the agent through ``POST /api/v1/agents`` and drives the routes
the web UI and the CLI call. ``agy`` is a stub on the front of ``PATH``; the
App bundle is covered by the probe's own tests.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.facets import put_programs_on_path

TOKEN = "test-token-agent-antigravity"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register(c: TestClient) -> str:
    r = c.post("/api/v1/agents", json={"type": "antigravity", "name": "antigravity"})
    assert r.status_code == 201, r.text
    return r.json()["uid"]


@pytest.mark.acceptance(
    spec="agent-registry/antigravity", scenario="discover Antigravity by its shared config folder"
)
def test_antigravity_is_found_at_gemini_config(tmp_path, monkeypatch):
    (tmp_path / ".gemini" / "config").mkdir(parents=True)
    put_programs_on_path(monkeypatch, tmp_path / "bin", {"agy": "agy 1.4.0"})
    app = _app(tmp_path, monkeypatch, 61400)
    with _client(app) as c:
        cands = {x["type"]: x for x in c.get("/api/v1/agents/candidates").json()["candidates"]}
        assert cands["antigravity"]["config_dir"] == str(tmp_path / ".gemini" / "config")
        assert cands["antigravity"]["state"] == "installed_active"

        uid = _register(c)
        agent = c.get(f"/api/v1/agents/{uid}").json()
        assert agent["config_dir"] == str(tmp_path / ".gemini" / "config")


@pytest.mark.acceptance(
    spec="agent-registry/antigravity",
    scenario="list exactly Antigravity's five shared config entries",
)
def test_antigravity_lists_exactly_its_shared_config_files(tmp_path, monkeypatch):
    cfg = tmp_path / ".gemini" / "config"
    cfg.mkdir(parents=True)
    data = tmp_path / ".gemini" / "antigravity"
    data.mkdir()
    (data / "mcp_oauth_tokens.json").write_text("{}", encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61410)
    with _client(app) as c:
        uid = _register(c)
        files = {f["key"]: f for f in c.get(f"/api/v1/agents/{uid}/config-files").json()["items"]}
        assert set(files) == {"mcp", "config", "instructions", "rules", "hooks"}
        assert files["mcp"]["path"] == str(cfg / "mcp_config.json")
        assert files["rules"]["path"] == str(cfg / "rules")
        assert all(str(data) not in f["path"] for f in files.values())


@pytest.mark.acceptance(
    spec="agent-registry/antigravity",
    scenario="install Coffer's MCP into an empty mcp_config.json",
)
def test_connect_writes_the_coffer_entry_into_an_empty_mcp_config(tmp_path, monkeypatch):
    cfg = tmp_path / ".gemini" / "config"
    cfg.mkdir(parents=True)
    mcp = cfg / "mcp_config.json"
    mcp.write_text("", encoding="utf-8")  # the App creates the file empty
    app = _app(tmp_path, monkeypatch, 61420)
    with _client(app) as c:
        uid = _register(c)
        r = c.post(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text

        entry = json.loads(mcp.read_text(encoding="utf-8"))["mcpServers"]["coffer"]
        assert entry["command"] == str(tmp_path / "coffer-mcp-shim")
        assert entry["args"] == ["--agent-uid", uid]
        assert entry["timeoutSeconds"] == 24 * 60 * 60
        assert (cfg / "skills").is_dir()


@pytest.mark.acceptance(
    spec="agent-registry/antigravity",
    scenario="read nothing from Antigravity's per-surface data folders",
)
def test_sessions_memory_and_plugins_read_empty(tmp_path, monkeypatch):
    (tmp_path / ".gemini" / "config").mkdir(parents=True)
    brain = tmp_path / ".gemini" / "antigravity" / "brain" / "c1"
    brain.mkdir(parents=True)
    (brain / "task.md").write_text("private", encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61430)
    with _client(app) as c:
        uid = _register(c)
        r = c.get(f"/api/v1/agents/{uid}/sessions")
        assert r.status_code == 400 and r.json()["error"]["code"] == "AGENT_TYPE_UNSUPPORTED"
        for path in ("plugins", "hooks"):
            r = c.get(f"/api/v1/agents/{uid}/{path}")
            assert r.status_code == 200, (path, r.text)
            body = r.json()
            items = body.get("items", body.get("hooks", body.get("own", [])))
            assert items == [], (path, body)
