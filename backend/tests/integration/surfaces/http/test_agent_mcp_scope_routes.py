"""Integration tests for GET/PUT /api/v1/agents/{name}/mcp-scope (ADR-026).

Full-app TestClient: the lifespan runs Alembic migrations (creating the
``agent_mcp_scope`` tables) and wires ``AgentMcpScopeService`` into the
composition root, so no dependency override is needed. The agent + mcp_server
resources are registered over HTTP so their ids resolve in the same DB.

The app MUST be entered via ``with _client(app) as c:`` so the lifespan runs.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-scope"
_FAKE = pathlib.Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register_agent(c: TestClient, tmp_path: pathlib.Path) -> None:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
    assert r.status_code == 201, r.text


def _register_server(c: TestClient, name: str) -> None:
    r = c.post(
        "/api/v1/resources",
        json={
            "kind": "mcp_server",
            "name": name,
            "config": {
                "transport": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [str(_FAKE), "--scenario", "basic", "--tools", "read_file"],
                },
            },
        },
    )
    assert r.status_code == 201, r.text


def test_get_scope_defaults_to_auto(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59800)
    with _client(app) as c:
        _register_agent(c, tmp_path)
        r = c.get("/api/v1/agents/cc/mcp-scope")
        assert r.status_code == 200, r.text
        assert r.json() == {"mode": "auto", "servers": []}


@pytest.mark.acceptance(spec="004-agent-registry", scenario="set an agent's MCP scope to selected")
def test_put_then_get_selected_scope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59810)
    with _client(app) as c:
        _register_agent(c, tmp_path)
        _register_server(c, "fs")
        _register_server(c, "git")

        r = c.put(
            "/api/v1/agents/cc/mcp-scope",
            json={"mode": "selected", "servers": ["fs"]},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"mode": "selected", "servers": ["fs"]}

        # GET reflects the persisted scope.
        r = c.get("/api/v1/agents/cc/mcp-scope")
        assert r.status_code == 200
        assert r.json() == {"mode": "selected", "servers": ["fs"]}


def test_put_unknown_server_is_422(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59820)
    with _client(app) as c:
        _register_agent(c, tmp_path)
        _register_server(c, "fs")
        r = c.put(
            "/api/v1/agents/cc/mcp-scope",
            json={"mode": "selected", "servers": ["ghost"]},
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "MCP_SCOPE_SERVER_UNKNOWN"


def test_get_unknown_agent_is_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59830)
    with _client(app) as c:
        r = c.get("/api/v1/agents/ghost/mcp-scope")
        assert r.status_code == 404, r.text


def test_put_unknown_agent_is_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59840)
    with _client(app) as c:
        r = c.put(
            "/api/v1/agents/ghost/mcp-scope",
            json={"mode": "auto", "servers": []},
        )
        assert r.status_code == 404, r.text
