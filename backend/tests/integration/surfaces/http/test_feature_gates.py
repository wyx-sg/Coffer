"""What a switched-off experimental feature closes, through the real daemon.

Spec experimental-features "Close every surface of a switched-off feature" and
"Keep what a switched-off feature holds". The routes, kinds and error hints are
exercised on the shipped features (``knowledge``, ``memory``);
the built-in tool mechanism, which needs a tool no shipped feature owns, runs
on a test-only feature registered beside them. Each test boots ``create_app``
under a throwaway HOME (database, knowledge and memory roots all in
``tmp_path``). Features are switched the way a person does — over REST —
on the same running process, so "without a restart" is what is being exercised.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.domain import features as domain_features
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.knowledge import fs
from coffer.infrastructure.knowledge.paths import knowledge_root
from coffer.surfaces.http import app as app_module
from coffer.surfaces.http import feature_dependencies
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.features import FAKE_FEATURE, enable_all_in_config, register_fake_feature
from tests.support.mcp_wire import INIT_PARAMS

_TOKEN = "test-token-feature-gates"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[pathlib.Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59780")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59789")
    monkeypatch.delenv(daemon_config.FEATURES_ENV, raising=False)
    (tmp_path / ".coffer").mkdir(parents=True, exist_ok=True)
    # Every feature is off until switched on: start from both on, so a test
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
    daemon_config.write_feature_setting("knowledge", False)
    with _client() as c:
        _assert_disabled(c.get("/api/v1/knowledge/collections"), "knowledge")
        # Only the feature's own prefix: everything else still answers.
        assert c.get("/api/v1/memory/partitions").status_code == 200
        assert c.get("/api/v1/sync/status").status_code == 200
        assert c.get("/api/v1/agents").status_code == 200


#: One real route per feature, and the key that closes it.
_ROUTE_OF = {
    "knowledge": "/api/v1/knowledge/collections",
    "memory": "/api/v1/memory/partitions",
}


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="knowledge off closes the knowledge routes",
)
@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="memory off closes the memory routes",
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
        # Always-on routes: conversations, what the agent pages and the
        # internal engine read, and the graduated sync and models routes.
        for always_on in (
            "/api/v1/sync/status",
            "/api/v1/providers",
            "/api/v1/agents",
            "/api/v1/agent-sessions",
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
        assert [f["key"] for f in listed] == ["knowledge", "memory"]
        status = c.get("/api/v1/daemon/status").json()
    assert set(status["features"]) == {"knowledge", "memory"}


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching a feature on opens its surfaces without a restart",
)
def test_switching_a_feature_on_opens_its_surfaces_without_a_restart(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon_config.write_feature_setting("memory", False)
    with _client() as c:
        _assert_disabled(c.get(_ROUTE_OF["memory"]), "memory")

        _switch(c, "memory", True)

        # Same process, same app: no restart between the switch and the answer.
        assert c.get(_ROUTE_OF["memory"]).status_code == 200
    assert _daemon_config(home)["features"]["memory"] is True


# --- hint ---------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a switched-off feature's refusal says how to switch it on",
)
def test_a_switched_off_features_command_says_how_to_switch_it_on(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("memory", False)
    daemon_config.write_feature_setting("knowledge", False)
    with _client() as c:
        for key, route in _ROUTE_OF.items():
            error = c.get(route).json()["error"]
            assert error["code"] == "FEATURE_DISABLED"
            assert "Settings › Features" in error["message"], key  # noqa: RUF001


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
        session = _mcp(c, None, "initialize", INIT_PARAMS).headers["mcp-session-id"]
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
        assert "coffer__search_tools" in names

        called = _mcp(c, session, "tools/call", {"name": fake_tool, "arguments": {}}).json()
        assert _unknown_as(called, unknown, fake_tool)

        _switch(c, FAKE_FEATURE, True)
        assert fake_tool in _tool_names(c, session)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="advertise coffer__search_tools as the one built-in tool"
)
def test_the_gateway_advertises_only_search_tools_as_a_built_in(home: pathlib.Path) -> None:
    def builtins(c: TestClient, session: str) -> set[str]:
        return {n for n in _tool_names(c, session) if n.startswith("coffer__")}

    with _client() as c:
        session = _mcp(c, None, "initialize", INIT_PARAMS).headers["mcp-session-id"]
        unknown = _mcp(
            c, session, "tools/call", {"name": "coffer__nosuchtool", "arguments": {}}
        ).json()

        assert builtins(c, session) == {"coffer__search_tools"}

        for name, arguments in (
            ("coffer__write", {"collection": "x", "title": "t", "description": "d"}),
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
        fs.write_file(
            directory="research",
            title="Lockfiles",
            description="How dependencies are pinned",
            body="Run uv sync --frozen.",
        )
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
    answers there with an experimental feature switched off."""
    daemon_config.write_feature_setting("memory", False)
    with _client() as c:
        status = c.get("/api/v1/daemon/status", headers={"X-Coffer-Token": ""}).json()
        _assert_disabled(c.get(_ROUTE_OF["memory"]), "memory")
        assert c.get("/api/v1/sync/status").status_code == 200
    assert status["machine_id"] == daemon_config.read_cached_machine_id()
    assert status["machine_id"]
    assert status["machine_name"] == daemon_config.read_machine_name()
    assert "channel" not in status
    assert status["features"] == {"knowledge": True, "memory": False}


# --- graduated features ----------------------------------------------------------


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="sync and models graduated and their switches are removed at startup",
)
def test_sync_and_models_switches_are_removed_and_their_routes_always_answer(
    home: pathlib.Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A machine where sync and models were switched off, and a daemon started
    with a ``COFFER_FEATURES`` pin naming them: at startup both switches leave
    ``daemon-config.json`` (the other keys stay), the pin's ``sync`` and
    ``models`` are unknown keys, and the sync and provider routes answer."""
    daemon_config.write_feature_setting("sync", False)
    daemon_config.write_feature_setting("models", False)
    daemon_config.write_feature_setting("from_newer_build", True)
    monkeypatch.setenv(daemon_config.FEATURES_ENV, "sync=off,models=off,memory=off")
    with caplog.at_level("WARNING"), _client() as c:
        for route in (
            "/api/v1/sync/status",
            "/api/v1/providers",
            "/api/v1/providers/price-list",
            "/api/v1/usage/summary",
            "/api/v1/proxy/status",
        ):
            assert c.get(route).status_code == 200, (route, c.get(route).text)
        # The pin still pins what the registry names.
        _assert_disabled(c.get(_ROUTE_OF["memory"]), "memory")
        listed = c.get("/api/v1/daemon/features").json()["features"]
        status = c.get("/api/v1/daemon/status").json()
    assert [f["key"] for f in listed] == ["knowledge", "memory"]
    assert status["features"] == {"knowledge": True, "memory": False}
    assert _daemon_config(home)["features"] == {
        "knowledge": True,
        "memory": True,
        "from_newer_build": True,
    }
    unknown = {
        r.args[1]
        for r in caplog.records
        if r.getMessage().startswith(f"{daemon_config.FEATURES_ENV} names unknown feature")
        and isinstance(r.args, tuple)
    }
    assert unknown == {"sync", "models"}
