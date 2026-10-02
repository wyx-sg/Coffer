"""What a switched-off experimental feature closes, through the real daemon.

Spec experimental-features "Close every surface of a switched-off feature" and
"Keep what a switched-off feature holds". The routes, kinds and CLI answers are
exercised on the shipped features (``knowledge``, ``memory``, ``sync``, ``models``);
the built-in tool mechanism, which needs a tool no shipped feature owns, runs
on a test-only feature registered beside them. Each test boots ``create_app``
under a throwaway HOME (database, knowledge and memory roots all in
``tmp_path``). Features are switched the way a person does — over REST or the
CLI — on the same running process, so "without a restart" is what is being
exercised.
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
from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.domain import features as domain_features
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.knowledge.paths import knowledge_root
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import app as app_module
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.features import FAKE_FEATURE, enable_all_in_config, register_fake_feature

_TOKEN = "test-token-feature-gates"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}

runner = CliRunner()


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59780")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59789")
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    (tmp_path / ".coffer").mkdir(parents=True, exist_ok=True)
    # Every feature is off until switched on: start from all four on, so a test
    # that switches one off is switching off what a person had switched on.
    enable_all_in_config()
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
    daemon_config.write_feature_setting("sync", False)
    with _client() as c:
        _assert_disabled(c.get("/api/v1/sync/status"), "sync")
        # Only the feature's own prefix: everything else still answers.
        assert c.get("/api/v1/knowledge/collections").status_code == 200
        assert c.get("/api/v1/memory/partitions").status_code == 200
        assert c.get("/api/v1/agents").status_code == 200


#: One real route per feature, and the key that closes it.
_ROUTE_OF = {
    "knowledge": "/api/v1/knowledge/collections",
    "memory": "/api/v1/memory/partitions",
    "sync": "/api/v1/sync/status",
    "models": "/api/v1/providers",
}


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="models off closes the provider, model, proxy and usage routes",
)
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="knowledge off closes the knowledge routes",
)
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="memory off closes the memory routes",
)
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="sync off closes the sync routes",
)
@pytest.mark.parametrize("key", sorted(_ROUTE_OF))
def test_each_experimental_feature_closes_only_its_own_routes(home: pathlib.Path, key: str) -> None:
    daemon_config.write_feature_setting(key, False)
    with _client() as c:
        for other, route in _ROUTE_OF.items():
            r = c.get(route)
            if other == key:
                _assert_disabled(r, key)
            else:
                assert r.status_code == 200, (other, r.text)
        # Always-on routes: conversations, and what the agent pages and the
        # internal engine read.
        for always_on in (
            "/api/v1/agents",
            "/api/v1/chat/conversations",
            "/api/v1/agent-providers",
            "/api/v1/internal-engine-config",
            "/api/v1/skills",
        ):
            assert c.get(always_on).status_code == 200, always_on


def test_every_route_under_a_features_prefixes_is_gated(home: pathlib.Path) -> None:
    """The registry's prefixes and the gated routers agree, route for route:
    no route of a switched-off feature is left answering."""
    registered = domain_features.EXPERIMENTAL_FEATURES
    for feature in registered:
        daemon_config.write_feature_setting(feature.key, False)
    with _client() as c:
        paths: dict[str, dict[str, Any]] = c.get("/api/v1/openapi.json").json()["paths"]
        checked: dict[str, int] = {f.key: 0 for f in registered}
        for feature in registered:
            for path, operations in paths.items():
                if not path.startswith(feature.route_prefixes):
                    continue
                url = re.sub(r"\{[^}]+\}", "x", path)
                for method in operations:
                    r = c.request(method.upper(), url, json={})
                    _assert_disabled(r, feature.key)
                    checked[feature.key] += 1
        # Every feature owns routes, and none of them leaked.
        assert all(n > 0 for n in checked.values()), checked
        assert c.get("/api/v1/agents").status_code == 200


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a stored setting for a feature the registry does not name is ignored",
)
def test_a_stored_setting_for_a_retired_feature_is_ignored(home: pathlib.Path) -> None:
    """A key the registry does not name — a feature since retired, or one a
    newer build wrote — fails nothing and is never listed."""
    daemon_config.write_feature_setting("vault_sync", False)
    daemon_config.write_feature_setting("retired_feature", False)
    with _client() as c:
        assert c.get("/api/v1/sync/status").status_code == 200
        listed = c.get("/api/v1/daemon/features").json()["features"]
        assert [f["key"] for f in listed] == ["knowledge", "memory", "sync", "models"]
        status = c.get("/api/v1/daemon/status").json()
    assert set(status["features"]) == {"knowledge", "memory", "sync", "models"}


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching a feature on opens its surfaces without a restart",
)
def test_switching_a_feature_on_opens_its_surfaces_without_a_restart(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon_config.write_feature_setting("sync", False)
    with _client() as c:
        _patch_cli(monkeypatch, c)
        _assert_disabled(c.get("/api/v1/sync/status"), "sync")

        res = runner.invoke(cli_app, ["config", "set", "feature.sync", "on"])
        assert res.exit_code == 0, res.output

        # Same process, same app: no restart between the switch and the answer.
        assert c.get("/api/v1/sync/status").status_code == 200
    assert _daemon_config(home)["features"]["sync"] is True


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
    daemon_config.write_feature_setting("sync", False)
    daemon_config.write_feature_setting("knowledge", False)
    with _client() as c:
        _patch_cli(monkeypatch, c)
        for key, argv in (("sync", ["sync", "status"]), ("knowledge", ["path", "knowledge"])):
            res = runner.invoke(cli_app, argv)
            assert res.exit_code == 1, res.output
            lines = [line for line in res.output.splitlines() if line.strip()]
            assert len(lines) == 1, res.output
            assert f"coffer config set feature.{key} on" in lines[0]


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


def _unknown_as(called: Any, unknown: Any, name: str) -> bool:
    """Whether ``called`` is exactly what an unknown tool answers, with the
    name swapped."""
    return json.dumps(called).replace(name, "coffer__nosuchtool") == json.dumps(unknown)


async def _fake_handler(_args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": "fake"}]}


@pytest.fixture
def fake_tool(monkeypatch: pytest.MonkeyPatch) -> str:
    """A fake feature owning one built-in tool, registered into the daemon's
    own tool registry as it is built. Returns the tool's listed name."""
    register_fake_feature(monkeypatch, route_prefixes=())

    class _WithFakeTool(BuiltinToolRegistry):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.register(
                BuiltinTool(
                    name="fake_tool",
                    description="A tool the fake feature owns.",
                    input_schema={"type": "object", "properties": {}},
                    handler=_fake_handler,
                    feature=FAKE_FEATURE,
                )
            )

    monkeypatch.setattr(app_module, "BuiltinToolRegistry", _WithFakeTool)
    return "coffer__fake_tool"


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a switched-off feature's tool leaves the tool list",
)
def test_a_switched_off_features_tool_leaves_the_tool_list(
    home: pathlib.Path, fake_tool: str
) -> None:
    with _client() as c:
        _switch(c, FAKE_FEATURE, True)
        session = _mcp(c, None, "initialize", {}).headers["mcp-session-id"]
        assert fake_tool in _tool_names(c, session)
        unknown = _mcp(
            c, session, "tools/call", {"name": "coffer__nosuchtool", "arguments": {}}
        ).json()

        # An unknown tool is refused, not served.
        assert "error" in unknown or unknown["result"].get("isError") is True, unknown

        _switch(c, FAKE_FEATURE, False)
        names = _tool_names(c, session)
        assert fake_tool not in names
        # Only the feature's tool; the always-on ones stay.
        assert {"coffer__search_tools", "coffer__write"} <= names

        called = _mcp(c, session, "tools/call", {"name": fake_tool, "arguments": {}}).json()
        assert _unknown_as(called, unknown, fake_tool)

        _switch(c, FAKE_FEATURE, True)
        assert fake_tool in _tool_names(c, session)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the gateway advertises exactly two built-in tools"
)
def test_the_gateway_advertises_exactly_two_built_in_tools(home: pathlib.Path) -> None:
    def builtins(c: TestClient, session: str) -> set[str]:
        return {n for n in _tool_names(c, session) if n.startswith("coffer__")}

    with _client() as c:
        session = _mcp(c, None, "initialize", {}).headers["mcp-session-id"]
        unknown = _mcp(
            c, session, "tools/call", {"name": "coffer__nosuchtool", "arguments": {}}
        ).json()

        assert builtins(c, session) == {"coffer__search_tools", "coffer__write"}

        for name, arguments in (
            ("coffer__recall", {"query": "x"}),
            ("coffer__diagnose", {"since_minutes": 5}),
        ):
            called = _mcp(c, session, "tools/call", {"name": name, "arguments": arguments})
            assert _unknown_as(called.json(), unknown, name), called.text


# --- data kept ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching a feature off and on keeps what it holds",
)
def test_switching_a_feature_off_and_on_keeps_what_it_holds(home: pathlib.Path) -> None:
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
        files_before = sorted(p.relative_to(home) for p in knowledge_root().rglob("*"))

        _switch(c, "knowledge", False)
        _assert_disabled(c.get("/api/v1/knowledge/collections"), "knowledge")
        assert sorted(p.relative_to(home) for p in knowledge_root().rglob("*")) == files_before

        _switch(c, "knowledge", True)
        assert c.get("/api/v1/knowledge/collections").json() == before
        assert c.get("/api/v1/knowledge/tree").json() == tree_before


# --- machine identity ---------------------------------------------------------------


@pytest.mark.acceptance(
    spec="daemon",
    scenario="daemon status names this machine and its features",
)
def test_the_status_names_this_machine_and_every_registered_feature(home: pathlib.Path) -> None:
    """Machine identity is not sync's: it rides on the daemon's own status, and
    answers there even while the feature owning the sync routes is off."""
    daemon_config.write_feature_setting("sync", False)
    with _client() as c:
        status = c.get("/api/v1/daemon/status", headers={"X-Coffer-Token": ""}).json()
        _assert_disabled(c.get("/api/v1/sync/status"), "sync")
    assert status["machine_id"] == daemon_config.read_cached_machine_id()
    assert status["machine_id"]
    assert status["machine_name"] == daemon_config.read_machine_name()
    assert "channel" not in status
    assert status["features"] == {"knowledge": True, "memory": True, "sync": False, "models": True}
