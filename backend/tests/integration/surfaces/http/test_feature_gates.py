"""What a switched-off experimental feature closes, through the real daemon.

Spec experimental-features "Close every surface of a switched-off feature",
"Keep what a switched-off feature holds" and "Withdraw what a switched-off
feature put in front of agents". Every test boots ``create_app`` under a
throwaway HOME (database, knowledge and memory roots all in ``tmp_path``), and
switches features the way a person does — over REST or the CLI — on the same
running process, so "without a restart" is what is being exercised.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as cli_client
from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.domain.features import EXPERIMENTAL_FEATURES
from coffer.domain.memory.delivery import MARKER
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-feature-gates"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}
_CATALOGUE_HEADING = "## What is in this developer's knowledge"

runner = CliRunner()


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59780")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59789")
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    (tmp_path / ".coffer").mkdir(parents=True, exist_ok=True)
    prior = feature_dependencies._feature_service
    yield tmp_path
    feature_dependencies._feature_service = prior


def _client() -> TestClient:
    app = create_app()
    set_active_token(_TOKEN)
    return TestClient(app, base_url="http://localhost", headers=_HEADERS)


def _switch(c: TestClient, key: str, enabled: bool) -> None:
    r = c.put(f"/api/v1/daemon/features/{key}", json={"enabled": enabled})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is enabled


def _daemon_config(home: pathlib.Path) -> dict[str, Any]:
    return json.loads((home / ".coffer" / "daemon-config.json").read_text())  # type: ignore[no-any-return]


def _assert_disabled(r: Any, key: str) -> None:
    assert r.status_code == 404, r.text
    error = r.json()["error"]
    assert error["code"] == "FEATURE_DISABLED"
    assert error["details"]["feature"] == key


# --- REST ---------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a switched-off feature's routes answer feature disabled",
)
def test_a_switched_off_features_routes_answer_feature_disabled(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("knowledge", False)
    with _client() as c:
        _assert_disabled(c.get("/api/v1/knowledge/collections"), "knowledge")
        # Only the feature that is off: the other two still answer.
        assert c.get("/api/v1/memory/partitions").status_code == 200
        assert c.get("/api/v1/sync/status").status_code == 200


def test_every_route_under_a_features_prefixes_is_gated(home: pathlib.Path) -> None:
    """The registry's prefixes and the gated routers agree, route for route:
    no route of a switched-off feature is left answering."""
    for feature in EXPERIMENTAL_FEATURES:
        daemon_config.write_feature_setting(feature.key, False)
    with _client() as c:
        paths: dict[str, dict[str, Any]] = c.get("/api/v1/openapi.json").json()["paths"]
        checked = 0
        for feature in EXPERIMENTAL_FEATURES:
            for path, operations in paths.items():
                if not path.startswith(feature.route_prefixes):
                    continue
                url = re.sub(r"\{[^}]+\}", "x", path)
                for method in operations:
                    r = c.request(method.upper(), url, json={})
                    _assert_disabled(r, feature.key)
                    checked += 1
        assert checked > 30
        # A route outside every feature is untouched by the switches: the
        # agent-registry's native-memory surface is the agent's, not Coffer's
        # memory layer's.
        assert c.get("/api/v1/agents").status_code == 200


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching a feature on opens its surfaces without a restart",
)
def test_switching_a_feature_on_opens_its_surfaces_without_a_restart(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon_config.write_feature_setting("vault_sync", False)
    with _client() as c:
        _patch_cli(monkeypatch, c)
        _assert_disabled(c.get("/api/v1/sync/status"), "vault_sync")

        res = runner.invoke(cli_app, ["daemon", "features", "enable", "vault_sync"])
        assert res.exit_code == 0, res.output

        # Same process, same app: no restart between the switch and the answer.
        assert c.get("/api/v1/sync/status").status_code == 200
    assert _daemon_config(home)["features"]["vault_sync"] is True


# --- CLI ----------------------------------------------------------------------


def _patch_cli(monkeypatch: pytest.MonkeyPatch, c: TestClient) -> None:
    """Point the CLI's daemon connection at the running app."""
    info = DaemonInfo(
        version=1,
        pid=4242,
        port=59780,
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

        def post(self, url: str, **kw: Any) -> Any:
            return self.request("POST", url, **kw)

        def put(self, url: str, **kw: Any) -> Any:
            return self.request("PUT", url, **kw)

        def delete(self, url: str, **kw: Any) -> Any:
            return self.request("DELETE", url, **kw)

    monkeypatch.setattr(cli_client, "client_or_exit", lambda: (_Persistent(c), info))


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a switched-off feature's command says how to switch it on",
)
def test_a_switched_off_features_command_says_how_to_switch_it_on(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon_config.write_feature_setting("vault_sync", False)
    with _client() as c:
        _patch_cli(monkeypatch, c)
        res = runner.invoke(cli_app, ["sync", "status"])
    assert res.exit_code == 1, res.output
    lines = [line for line in res.output.splitlines() if line.strip()]
    assert len(lines) == 1, res.output
    assert "coffer daemon features enable vault_sync" in lines[0]


# --- MCP ----------------------------------------------------------------------


def _mcp(c: TestClient, session: str | None, method: str, params: dict[str, Any]) -> Any:
    headers = {**_HEADERS, **({"Mcp-Session-Id": session} if session else {})}
    r = c.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r


def _tool_names(c: TestClient, session: str) -> set[str]:
    return {t["name"] for t in _mcp(c, session, "tools/list", {}).json()["result"]["tools"]}


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a switched-off feature's tool leaves the tool list",
)
def test_a_switched_off_features_tool_leaves_the_tool_list(home: pathlib.Path) -> None:
    with _client() as c:
        session = _mcp(c, None, "initialize", {}).headers["mcp-session-id"]
        assert "coffer__recall" in _tool_names(c, session)
        unknown = _mcp(
            c, session, "tools/call", {"name": "coffer__nosuchtool", "arguments": {}}
        ).json()

        # An unknown tool is refused, not served.
        assert "error" in unknown or unknown["result"].get("isError") is True, unknown

        _switch(c, "memory", False)
        names = _tool_names(c, session)
        assert "coffer__recall" not in names
        # Only the memory feature's tool; the always-on ones stay.
        assert {"coffer__search_tools", "coffer__diagnose", "coffer__write"} <= names

        called = _mcp(
            c, session, "tools/call", {"name": "coffer__recall", "arguments": {"query": "x"}}
        ).json()
        # Exactly what an unknown tool answers, with the name swapped.
        assert json.dumps(called).replace("coffer__recall", "coffer__nosuchtool") == json.dumps(
            unknown
        )

        _switch(c, "memory", True)
        assert "coffer__recall" in _tool_names(c, session)


def test_knowledge_off_takes_coffer_write_out_of_the_list(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("knowledge", False)
    with _client() as c:
        session = _mcp(c, None, "initialize", {}).headers["mcp-session-id"]
        names = _tool_names(c, session)
    assert "coffer__write" not in names
    assert "coffer__recall" in names


# --- data kept ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching knowledge off and on keeps the collections",
)
def test_switching_knowledge_off_and_on_keeps_the_collections(home: pathlib.Path) -> None:
    with _client() as c:
        r = c.post("/api/v1/knowledge/collections", json={"name": "research"})
        assert r.status_code == 201, r.text
        r = c.post(
            "/api/v1/knowledge/material",
            json={
                "collection": "research",
                "title": "Lockfiles",
                "description": "How dependencies are pinned",
                "body": "Run uv sync --frozen.",
            },
        )
        assert r.status_code == 201, r.text
        before = c.get("/api/v1/knowledge/collections").json()
        tree_before = c.get("/api/v1/knowledge/tree").json()
        files_before = sorted(p.relative_to(home) for p in (home / "knowledge").rglob("*"))

        _switch(c, "knowledge", False)
        _assert_disabled(c.get("/api/v1/knowledge/collections"), "knowledge")
        assert sorted(p.relative_to(home) for p in (home / "knowledge").rglob("*")) == files_before

        _switch(c, "knowledge", True)
        assert c.get("/api/v1/knowledge/collections").json() == before
        assert c.get("/api/v1/knowledge/tree").json() == tree_before


# --- what was put in front of agents -----------------------------------------


def _hook_installed(config_dir: pathlib.Path) -> bool:
    settings = config_dir / "settings.json"
    return settings.is_file() and f": {MARKER}" in settings.read_text()


def _agent_with_hook(c: TestClient, home: pathlib.Path) -> tuple[str, pathlib.Path]:
    config_dir = home / "cc-config"
    config_dir.mkdir()
    r = c.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "cc", "config_dir": str(config_dir)},
    )
    assert r.status_code == 201, r.text
    uid = str(r.json()["uid"])
    r = c.post(f"/api/v1/memory/delivery/{uid}/install")
    assert r.status_code == 200, r.text
    assert _hook_installed(config_dir)
    return uid, config_dir


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching memory off removes the delivery hook",
)
def test_switching_memory_off_removes_the_delivery_hook(home: pathlib.Path) -> None:
    with _client() as c:
        uid, config_dir = _agent_with_hook(c, home)

        _switch(c, "memory", False)
        assert not _hook_installed(config_dir)
        assert _daemon_config(home)["memory_delivery_withdrawn"] == [uid]

        _switch(c, "memory", True)
        assert _hook_installed(config_dir)
        assert _daemon_config(home)["memory_delivery_withdrawn"] == []


def test_the_withdrawn_hook_comes_back_across_a_restart(home: pathlib.Path) -> None:
    """Off, restart, on: the list of agents to put the hook back into is kept
    with the switch, not in the process."""
    with _client() as c:
        _uid, config_dir = _agent_with_hook(c, home)
        _switch(c, "memory", False)
    with _client() as c:
        assert not _hook_installed(config_dir)
        _switch(c, "memory", True)
        assert _hook_installed(config_dir)


def test_a_boot_with_memory_off_removes_a_hook_left_in_place(home: pathlib.Path) -> None:
    with _client() as c:
        _uid, config_dir = _agent_with_hook(c, home)
    daemon_config.write_feature_setting("memory", False)
    with _client():
        assert not _hook_installed(config_dir)


def _guide(home: pathlib.Path) -> str:
    return (home / ".coffer" / "skills" / GUIDE_SKILL_NAME / "SKILL.md").read_text()


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching knowledge off drops the catalogue from the guide",
)
def test_switching_knowledge_off_drops_the_catalogue_from_the_guide(home: pathlib.Path) -> None:
    with _client() as c:
        r = c.post(
            "/api/v1/knowledge/collections",
            json={"name": "shopee", "description": "Shopee's account system."},
        )
        assert r.status_code == 201, r.text
        assert _CATALOGUE_HEADING in _guide(home)
        assert "### shopee" in _guide(home)

        _switch(c, "knowledge", False)
        text = _guide(home)
        assert _CATALOGUE_HEADING not in text
        assert "shopee" not in text
        assert "coffer__write" not in text.split("---")[1]  # the description

        _switch(c, "knowledge", True)
        assert "### shopee" in _guide(home)


def test_a_boot_with_knowledge_off_renders_the_guide_without_the_catalogue(
    home: pathlib.Path,
) -> None:
    with _client() as c:
        r = c.post("/api/v1/knowledge/collections", json={"name": "shopee"})
        assert r.status_code == 201, r.text
    daemon_config.write_feature_setting("knowledge", False)
    with _client():
        assert _CATALOGUE_HEADING not in _guide(home)


# --- machine identity outlives the sync surface ----------------------------------


@pytest.mark.acceptance(
    spec="daemon",
    scenario="daemon status names this machine and its features",
)
def test_the_status_names_this_machine_while_sync_is_off(home: pathlib.Path) -> None:
    """Machine identity is not sync's: a channel is bound to a machine whether or
    not ``vault_sync`` is on, so the id the sync surface used to be the only
    source of rides on the daemon's own status too."""
    daemon_config.write_feature_setting("vault_sync", False)
    with _client() as c:
        status = c.get("/api/v1/daemon/status", headers={"X-Coffer-Token": ""}).json()
        _assert_disabled(c.get("/api/v1/sync/status"), "vault_sync")
    assert status["machine_id"] == daemon_config.read_cached_machine_id()
    assert status["machine_id"]
    assert status["machine_name"] == daemon_config.read_machine_name()
    assert status["channel"] in ("stable", "dev")
    assert status["features"] == {"vault_sync": False, "knowledge": True, "memory": True}


def test_a_channel_bound_here_registers_while_sync_is_off(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon_config.write_feature_setting("vault_sync", False)
    with _client() as c:
        _patch_cli(monkeypatch, c)
        machine_id = c.get("/api/v1/daemon/status").json()["machine_id"]
        (home / "cc-config").mkdir()
        agent = c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "cc", "config_dir": str(home / "cc-config")},
        )
        assert agent.status_code == 201, agent.text
        stored = c.post("/api/v1/credentials", json={"ref": "tg-token", "value": "123:abc"})
        assert stored.status_code == 204, stored.text
        res = runner.invoke(
            cli_app,
            [
                "channel",
                "register",
                "tg",
                "--type",
                "telegram",
                "--bot-token-ref",
                "tg-token",
                "--agent",
                "cc",
            ],
        )
        channels = c.get("/api/v1/resources", params={"kind": "channel"}).json()
    assert res.exit_code == 0, res.output
    [channel] = channels["resources"]
    assert channel["config"]["runs_on"] == machine_id


def test_curate_owner_show_answers_while_sync_is_off(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon_config.write_feature_setting("vault_sync", False)
    with _client() as c:
        _patch_cli(monkeypatch, c)
        res = runner.invoke(cli_app, ["engine", "curate-owner", "show", "--json"])
    assert res.exit_code == 0, res.output
