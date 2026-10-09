"""An agent's Coffer connection, through the real daemon and the CLI.

Spec agent-registry "Connect an agent to Coffer in one action", "Report an
agent's Coffer connection part by part", "Disconnect an agent from Coffer".
Every test boots ``create_app`` under a throwaway HOME with a deterministic shim
path, registers a Claude Code agent there, and reads what landed in that
agent's own ``~/.claude.json``, where the gateway entry lands.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.daemon import config as daemon_config
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.features import enable_all_in_config

_TOKEN = "test-token-agent-connection"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59830")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59839")
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    enable_all_in_config()
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    (tmp_path / ".coffer").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude").mkdir()
    prior = feature_dependencies._feature_service
    yield tmp_path
    feature_dependencies._feature_service = prior


def _client() -> TestClient:
    app = create_app()
    set_active_token(_TOKEN)
    return TestClient(app, base_url="http://localhost", headers=_HEADERS)


def _register(c: TestClient) -> str:
    r = c.post("/api/v1/agents", json={"type": "claude_code"})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _claude_json(home: pathlib.Path) -> dict[str, Any]:
    path = home / ".claude.json"
    return json.loads(path.read_text()) if path.is_file() else {}  # type: ignore[no-any-return]


def _audit_types(c: TestClient, uid: str) -> list[str]:
    r = c.get("/api/v1/audit", params={"resource_uid": uid, "limit": 200})
    assert r.status_code == 200, r.text
    return [e["event_type"] for e in r.json()["entries"]]


def _connection_events(c: TestClient, uid: str) -> list[str]:
    """The audit entries a connection writes — not the daemon's own background
    passes that land on the same agent."""
    return [t for t in _audit_types(c, uid) if t.startswith("agent_mcp_")]


def _parts(body: dict[str, Any]) -> dict[str, bool]:
    return {p["key"]: p["installed"] for p in body["parts"]}


@pytest.mark.acceptance(spec="agent-registry", scenario="connect installs every part that applies")
@pytest.mark.acceptance(
    spec="agent-registry", scenario="read an agent's connection without writing anything"
)
def test_connect_installs_the_gateway_entry(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _register(c)
        before = c.get(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert before["state"] == "disconnected"
        assert _parts(before) == {"mcp": False}

        r = c.post(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] == "connected"
        assert _parts(body) == {"mcp": True}
        # The part says what it installed: the shim for the gateway entry.
        details = {p["key"]: p["detail"] for p in body["parts"]}
        assert details["mcp"] == str(home / "coffer-mcp-shim")
        assert _claude_json(home)["mcpServers"]["coffer"]["args"] == ["--agent-uid", uid]

        events = _audit_types(c, uid)
        assert events.count("agent_mcp_installed") == 1
        entries = c.get("/api/v1/audit", params={"resource_uid": uid, "limit": 200}).json()
        actors = {
            e["actor"] for e in entries["entries"] if e["event_type"] == "agent_mcp_installed"
        }
        assert actors == {"user"}
        # Reading the connection writes and audits nothing.
        audit_before = _connection_events(c, uid)
        written = (home / ".claude.json").stat().st_mtime_ns
        after = c.get(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert after["state"] == "connected" and _parts(after) == {"mcp": True}
        assert (home / ".claude.json").stat().st_mtime_ns == written
        assert _connection_events(c, uid) == audit_before


@pytest.mark.acceptance(spec="agent-registry", scenario="disconnect removes only Coffer's entries")
def test_disconnect_removes_only_coffers_entries(home: pathlib.Path) -> None:
    (home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "other-server"}}}), encoding="utf-8"
    )
    foreign = {"type": "command", "command": "echo foreign"}
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"SessionStart": [{"hooks": [foreign]}]}, "env": {"A": "1"}}),
        encoding="utf-8",
    )
    with _client() as c:
        uid = _register(c)
        assert c.post(f"/api/v1/agents/{uid}/coffer-connection").json()["state"] == "connected"

        r = c.delete(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "disconnected"
        assert _claude_json(home)["mcpServers"] == {"other": {"command": "other-server"}}
        settings = json.loads((home / ".claude" / "settings.json").read_text())
        assert settings["hooks"]["SessionStart"] == [{"hooks": [foreign]}]
        assert settings["env"] == {"A": "1"}
        events = _connection_events(c, uid)
        assert events.count("agent_mcp_uninstalled") == 1

        claude_mtime = (home / ".claude.json").stat().st_mtime_ns
        settings_mtime = (home / ".claude" / "settings.json").stat().st_mtime_ns
        again = c.delete(f"/api/v1/agents/{uid}/coffer-connection")
        assert again.status_code == 200
        assert again.json()["state"] == "disconnected"
        assert (home / ".claude.json").stat().st_mtime_ns == claude_mtime
        assert (home / ".claude" / "settings.json").stat().st_mtime_ns == settings_mtime
        assert _connection_events(c, uid) == events


def test_connection_routes_404_for_an_unknown_agent(home: pathlib.Path) -> None:
    with _client() as c:
        for method in ("GET", "POST", "DELETE"):
            r = c.request(method, "/api/v1/agents/ghost/coffer-connection")
            assert r.status_code == 404, f"{method}: {r.text}"


def test_connect_without_a_shim_is_refused_and_writes_nothing(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(home / "absent-shim"))
    # Nothing on PATH but git, which the daemon needs to open the vault.
    git = shutil.which("git")
    assert git is not None
    monkeypatch.setenv("PATH", os.pathsep.join([str(home / "empty-bin"), os.path.dirname(git)]))
    monkeypatch.setattr(
        "coffer.application.agent.mcp_service.sysconfig.get_path", lambda _name: None
    )
    monkeypatch.setattr("coffer.application.agent.mcp_service.sys.executable", "/nonexistent/py")
    with _client() as c:
        uid = _register(c)
        r = c.post(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code == 422, r.text
        assert "coffer-mcp-shim" in r.text
    assert not (home / ".claude.json").exists()
