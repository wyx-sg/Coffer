"""An agent's Coffer connection, through the real daemon and the CLI.

Spec agent-registry "Connect an agent to Coffer in one action", "Report an
agent's Coffer connection part by part", "Disconnect an agent from Coffer".
Every test boots ``create_app`` under a throwaway HOME with a deterministic shim
path, registers a Claude Code agent there, and reads what landed in that
agent's own files — ``~/.claude.json`` for the gateway entry, ``settings.json``
for the memory hook.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as cli_client
from coffer.domain.memory.delivery import MARKER
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-agent-connection"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}

runner = CliRunner()


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59830")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59839")
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
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
    r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _claude_json(home: pathlib.Path) -> dict[str, Any]:
    path = home / ".claude.json"
    return json.loads(path.read_text()) if path.is_file() else {}  # type: ignore[no-any-return]


def _settings_text(home: pathlib.Path) -> str:
    path = home / ".claude" / "settings.json"
    return path.read_text() if path.is_file() else ""


def _hook_installed(home: pathlib.Path) -> bool:
    return f": {MARKER}" in _settings_text(home)


def _audit_types(c: TestClient, uid: str) -> list[str]:
    r = c.get("/api/v1/audit", params={"resource_id": uid, "limit": 200})
    assert r.status_code == 200, r.text
    return [e["event_type"] for e in r.json()["entries"]]


def _parts(body: dict[str, Any]) -> dict[str, bool]:
    return {p["key"]: p["installed"] for p in body["parts"]}


@pytest.mark.acceptance(spec="agent-registry", scenario="connect installs every part that applies")
def test_connect_installs_the_gateway_entry_and_the_memory_hook(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("memory", True)
    with _client() as c:
        uid = _register(c)
        before = c.get(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert before["state"] == "disconnected"
        assert _parts(before) == {"mcp": False, "memory_hook": False}

        r = c.post(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] == "connected"
        assert _parts(body) == {"mcp": True, "memory_hook": True}
        # Each part says what it installed: the shim for the gateway entry,
        # the marked command for the hook.
        details = {p["key"]: p["detail"] for p in body["parts"]}
        assert details["mcp"] == str(home / "coffer-mcp-shim")
        assert details["memory_hook"] is not None
        assert details["memory_hook"].startswith(f": {MARKER};")

        assert _claude_json(home)["mcpServers"]["coffer"]["args"] == ["--agent-uid", uid]
        assert _hook_installed(home)

        events = _audit_types(c, uid)
        assert events.count("agent_mcp_installed") == 1
        assert events.count("memory_delivery_installed") == 1
        entries = c.get("/api/v1/audit", params={"resource_id": uid, "limit": 200}).json()
        actors = {
            e["actor"]
            for e in entries["entries"]
            if e["event_type"] in ("agent_mcp_installed", "memory_delivery_installed")
        }
        assert actors == {"user"}


@pytest.mark.acceptance(
    spec="agent-registry", scenario="connect leaves out a part whose feature is off"
)
def test_connect_with_memory_off_installs_only_the_gateway_entry(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("memory", False)
    with _client() as c:
        uid = _register(c)
        body = c.post(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert body["state"] == "connected"
        assert [p["key"] for p in body["parts"]] == ["mcp"]
        assert "coffer" in _claude_json(home)["mcpServers"]
        assert not _hook_installed(home)
        assert "memory_delivery_installed" not in _audit_types(c, uid)


@pytest.mark.acceptance(spec="agent-registry", scenario="report a partly installed connection")
def test_a_connection_missing_the_hook_reads_partial_and_connect_repairs_it(
    home: pathlib.Path,
) -> None:
    # Connected while memory was off: the gateway entry only.
    daemon_config.write_feature_setting("memory", False)
    with _client() as c:
        uid = _register(c)
        c.post(f"/api/v1/agents/{uid}/coffer-connection")
    # A later boot with memory on does not install the hook by itself — the
    # page reports the gap, and connecting is the act that closes it.
    daemon_config.write_feature_setting("memory", True)
    with _client() as c:
        audit_before = _audit_types(c, uid)
        status = c.get(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert status["state"] == "partial"
        assert _parts(status) == {"mcp": True, "memory_hook": False}
        mcp_part = next(p for p in status["parts"] if p["key"] == "mcp")
        assert mcp_part["detail"] == str(home / "coffer-mcp-shim")
        assert not _hook_installed(home)
        # Reading the connection writes and audits nothing.
        assert _audit_types(c, uid) == audit_before

        repaired = c.post(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert repaired["state"] == "connected"
        assert _hook_installed(home)


@pytest.mark.acceptance(spec="agent-registry", scenario="disconnect removes only Coffer's entries")
def test_disconnect_removes_only_coffers_entries(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("memory", True)
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
        settings = json.loads(_settings_text(home))
        assert settings["hooks"]["SessionStart"] == [{"hooks": [foreign]}]
        assert settings["env"] == {"A": "1"}
        events = _audit_types(c, uid)
        assert events.count("agent_mcp_uninstalled") == 1
        assert events.count("memory_delivery_removed") == 1

        claude_mtime = (home / ".claude.json").stat().st_mtime_ns
        settings_mtime = (home / ".claude" / "settings.json").stat().st_mtime_ns
        again = c.delete(f"/api/v1/agents/{uid}/coffer-connection")
        assert again.status_code == 200
        assert again.json()["state"] == "disconnected"
        assert (home / ".claude.json").stat().st_mtime_ns == claude_mtime
        assert (home / ".claude" / "settings.json").stat().st_mtime_ns == settings_mtime
        assert _audit_types(c, uid) == events


def test_disconnect_takes_out_a_hook_left_while_memory_is_off(home: pathlib.Path) -> None:
    """A part that does not apply now is still Coffer's to remove."""
    daemon_config.write_feature_setting("memory", True)
    with _client() as c:
        uid = _register(c)
        c.post(f"/api/v1/agents/{uid}/coffer-connection")
    daemon_config.write_feature_setting("memory", False)
    # Put a hook back by hand, as a stale one would be.
    with _client() as c:
        assert not _hook_installed(home)  # the boot withdrew it
    (home / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [{"hooks": [{"type": "command", "command": f": {MARKER}; x"}]}]
                }
            }
        ),
        encoding="utf-8",
    )
    with _client() as c:
        # Not applicable, so not listed…
        status = c.get(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert [p["key"] for p in status["parts"]] == ["mcp"]
        # …but a disconnect removes it all the same.
        c.delete(f"/api/v1/agents/{uid}/coffer-connection")
    assert not _hook_installed(home)
    assert "coffer" not in _claude_json(home).get("mcpServers", {})


def test_connection_routes_404_for_an_unknown_agent(home: pathlib.Path) -> None:
    with _client() as c:
        for method in ("GET", "POST", "DELETE"):
            r = c.request(method, "/api/v1/agents/ghost/coffer-connection")
            assert r.status_code == 404, f"{method}: {r.text}"


def test_connect_without_a_shim_is_refused_and_writes_nothing(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(home / "absent-shim"))
    monkeypatch.setenv("PATH", str(home / "empty-bin"))
    monkeypatch.setattr(
        "coffer.application.agent.mcp_service.sysconfig.get_path", lambda _name: None
    )
    monkeypatch.setattr("coffer.application.agent.mcp_service.sys.executable", "/nonexistent/py")
    daemon_config.write_feature_setting("memory", True)
    with _client() as c:
        uid = _register(c)
        r = c.post(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code == 422, r.text
        assert "coffer-mcp-shim" in r.text
    assert not (home / ".claude.json").exists()
    assert not _hook_installed(home)


# --- CLI ----------------------------------------------------------------------


def _patch_cli(monkeypatch: pytest.MonkeyPatch, c: TestClient) -> None:
    """Point the CLI's daemon connection at the running app."""
    info = DaemonInfo(
        version=1,
        pid=4242,
        port=59830,
        token=_TOKEN,
        started_at=datetime.now(tz=UTC),
        binary_path="/test",
    )

    class _Persistent:
        def __init__(self, inner: TestClient) -> None:
            self._inner = inner
            self.base_url = "http://localhost/api/v1"

        def __enter__(self) -> _Persistent:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def request(self, method: str, url: str, **kw: Any) -> Any:
            return self._inner.request(method, "/api/v1" + url, **kw)

        def get(self, url: str, **kw: Any) -> Any:
            return self.request("GET", url, **kw)

    monkeypatch.setattr(cli_client, "client_or_exit", lambda: (_Persistent(c), info))


@pytest.mark.acceptance(
    spec="agent-registry", scenario="config-file and MCP operations mirror across surfaces"
)
def test_cli_connect_connection_and_disconnect(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon_config.write_feature_setting("memory", True)
    with _client() as c:
        uid = _register(c)
        _patch_cli(monkeypatch, c)

        res = runner.invoke(cli_app, ["agent", "connection", "cc", "--json"])
        assert res.exit_code == 0, res.output
        assert json.loads(res.output)["state"] == "disconnected"

        res = runner.invoke(cli_app, ["agent", "connect", "cc"])
        assert res.exit_code == 0, res.output
        assert "connected agent cc to Coffer" in res.output
        assert "gateway MCP entry: installed" in res.output
        assert "memory delivery hook: installed" in res.output
        rest = c.get(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert rest["state"] == "connected"

        res = runner.invoke(cli_app, ["agent", "connection", "cc"])
        assert res.exit_code == 0, res.output
        assert res.output.splitlines()[0] == "cc: connected"

        res = runner.invoke(cli_app, ["agent", "disconnect", "cc"])
        assert res.exit_code == 0, res.output
        assert "disconnected agent cc from Coffer" in res.output
        assert c.get(f"/api/v1/agents/{uid}/coffer-connection").json()["state"] == "disconnected"


def test_cli_connection_reads_needs_repair_for_a_partial_connection(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon_config.write_feature_setting("memory", True)
    with _client() as c:
        _register(c)
        _patch_cli(monkeypatch, c)
        runner.invoke(cli_app, ["agent", "connect", "cc"])
        (home / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
        res = runner.invoke(cli_app, ["agent", "connection", "cc"])
        assert res.exit_code == 0, res.output
        assert "needs repair" in res.output
        assert "memory delivery hook: missing" in res.output


def test_cli_connect_unknown_agent_exits_non_zero(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client() as c:
        _patch_cli(monkeypatch, c)
        res = runner.invoke(cli_app, ["agent", "connect", "ghost"])
        assert res.exit_code != 0
