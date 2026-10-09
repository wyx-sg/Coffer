"""``POST /api/v1/daemon/uninstall`` through the real daemon (spec daemon
"Uninstall Coffer from this machine").

Each test boots ``create_app`` under a throwaway HOME, puts Coffer's footprints
where a real install leaves them — a connected Claude Code agent, the
installer's ``PATH`` block in ``~/.zshrc``, ``~/.coffer/bin``, a Warp launch
file — and reads what is left. The daemon's own stop is replaced by a recorder:
in a test it would signal the test run.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from coffer.application.secret.presence import derive_grant_key, sign_grant
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon import data_purge
from coffer.surfaces.http import daemon_uninstall_routes, feature_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.secret_composition import get_master_key_manager
from tests.fixtures.keyring import install_in_memory_keyring
from tests.support.features import enable_all_in_config

_TOKEN = "test-token-uninstall"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}
_BLOCK = '\n# Added by Coffer installer\nexport PATH="$HOME/.coffer/bin:$PATH"\n'


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    install_in_memory_keyring(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ZDOTDIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59850")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59859")
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    enable_all_in_config()
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    (tmp_path / ".coffer" / "bin" / "0.3.0").mkdir(parents=True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".zshrc").write_text("export EDITOR=vim\n" + _BLOCK)
    warp = tmp_path / ".warp" / "launch_configurations"
    warp.mkdir(parents=True)
    (warp / "coffer-1.yaml").write_text("x")
    prior = feature_dependencies._feature_service
    yield tmp_path
    feature_dependencies._feature_service = prior
    data_purge._purge_on_exit = False


@pytest.fixture
def stops(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    calls: list[bool] = []
    monkeypatch.setattr(daemon_uninstall_routes, "_schedule_shutdown", lambda: calls.append(True))
    monkeypatch.setattr(daemon_uninstall_routes, "_STOP_DELAY_SECONDS", 0.0)
    return calls


def _client() -> TestClient:
    set_active_token(_TOKEN)
    return TestClient(create_app(), base_url="http://localhost", headers=_HEADERS)


def _connected_agent(c: TestClient) -> str:
    r = c.post("/api/v1/agents", json={"type": "claude_code"})
    assert r.status_code == 201, r.text
    uid = str(r.json()["uid"])
    assert c.post(f"/api/v1/agents/{uid}/coffer-connection").status_code == 200
    return uid


def _gateway(home: pathlib.Path) -> object:
    path = home / ".claude.json"
    servers = json.loads(path.read_text()).get("mcpServers", {}) if path.is_file() else {}
    return servers.get("coffer")


@pytest.mark.acceptance(
    spec="daemon", scenario="uninstall removes every footprint and keeps the vault"
)
def test_uninstall_removes_coffers_footprint_and_keeps_the_vault(
    home: pathlib.Path, stops: list[bool]
) -> None:
    with _client() as c:
        uid = _connected_agent(c)
        assert _gateway(home) is not None
        vault = sorted(p.name for p in (home / ".coffer" / "vault").iterdir())
        r = c.post("/api/v1/daemon/uninstall", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        status = c.get(f"/api/v1/agents/{uid}/coffer-connection").json()
    steps = {s["key"]: s["outcome"] for s in body["steps"]}
    assert steps["agent_connections"] == "done"
    assert steps["path_lines"] == "done"
    assert steps["binaries"] == "done"
    assert steps["terminal_files"] == "done"
    assert body["deletes_data"] is False
    assert _gateway(home) is None
    assert status["state"] == "disconnected"
    assert (home / ".zshrc").read_text() == "export EDITOR=vim\n"
    assert not (home / ".coffer" / "bin").exists()
    assert not list((home / ".warp" / "launch_configurations").iterdir())
    assert sorted(p.name for p in (home / ".coffer" / "vault").iterdir()) == vault
    assert stops == [True]
    assert data_purge._purge_on_exit is False


@pytest.mark.acceptance(spec="daemon", scenario="deleting the data needs a presence grant")
def test_deleting_the_data_without_a_grant_removes_nothing(
    home: pathlib.Path, stops: list[bool]
) -> None:
    with _client() as c:
        _connected_agent(c)
        missing = c.post("/api/v1/daemon/uninstall", json={"delete_data": True})
        forged = c.post(
            "/api/v1/daemon/uninstall",
            json={"delete_data": True, "nonce": "n", "signature": "00"},
        )
    assert missing.status_code == 403
    assert forged.status_code >= 400
    assert _gateway(home) is not None
    assert (home / ".coffer" / "bin").exists()
    assert stops == []
    assert data_purge._purge_on_exit is False


def test_a_signed_grant_has_the_data_deleted_once_the_daemon_stops(
    home: pathlib.Path, stops: list[bool]
) -> None:
    with _client() as c:
        challenge = c.post(
            "/api/v1/secrets/presence/challenge", json={"op": "uninstall", "target": "delete-data"}
        ).json()
        key = derive_grant_key(get_master_key_manager().current or b"")
        signature = sign_grant(key, "uninstall", "delete-data", challenge["nonce"])
        r = c.post(
            "/api/v1/daemon/uninstall",
            json={"delete_data": True, "nonce": challenge["nonce"], "signature": signature},
        )
    assert r.status_code == 200, r.text
    assert r.json()["deletes_data"] is True
    # Nothing is deleted while the daemon serves; its exit path does it.
    assert (home / ".coffer").exists()
    assert data_purge._purge_on_exit is True
