"""What a switched-off feature closes beyond its own routes, through the real daemon.

Spec experimental-features "Close every surface of a switched-off feature" and
"Withdraw what a switched-off feature put in front of agents": a feature's
resources are out of reach of the kind-agnostic resource routes, and the
handshake instructions name only the tools the tool list carries.

Boots ``create_app`` under a throwaway HOME, with the fixtures and helpers of
``test_feature_gates``; the kinds are exercised on the shipped features, the
tool mechanism on a test-only one registered beside them.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.knowledge.paths import knowledge_root
from tests.integration.surfaces.http import test_feature_gates as gates
from tests.support.features import FAKE_FEATURE
from tests.support.mcp_wire import INIT_PARAMS

home = gates.home
fake_tool = gates.fake_tool
_assert_disabled = gates._assert_disabled
_client = gates._client
_switch = gates._switch


def _collection(c: TestClient, name: str) -> str:
    r = c.post("/api/v1/knowledge/collections", json={"name": name})
    assert r.status_code == 201, r.text
    [row] = [
        r
        for r in c.get("/api/v1/resources", params={"kind": "knowledge"}).json()["resources"]
        if r["name"] == name
    ]
    return str(row["uid"])


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="a switched-off feature's resources are out of reach of the resource routes",
)
def test_a_switched_off_features_resources_are_out_of_reach(home: pathlib.Path) -> None:
    with _client() as c:
        uid = _collection(c, "research")
        folder = knowledge_root() / "research"
        assert folder.is_dir()

        _switch(c, "knowledge", False)
        base = f"/api/v1/resources/{uid}"
        _assert_disabled(c.get("/api/v1/resources", params={"kind": "knowledge"}), "knowledge")
        _assert_disabled(c.get(base), "knowledge")
        _assert_disabled(c.patch(base, json={"description": "x"}), "knowledge")
        _assert_disabled(c.delete(base), "knowledge")
        _assert_disabled(c.post(f"{base}/enable"), "knowledge")
        _assert_disabled(c.post(f"{base}/disable"), "knowledge")
        _assert_disabled(c.get(f"{base}/scope"), "knowledge")
        _assert_disabled(c.put(f"{base}/scope", json={"scope": None}), "knowledge")
        _assert_disabled(
            c.post("/api/v1/resources", json={"kind": "knowledge", "name": "x", "config": {}}),
            "knowledge",
        )
        listed = c.get("/api/v1/resources").json()["resources"]
        assert all(r["kind"] != "knowledge" for r in listed)
        # A kind no feature owns is untouched by the switch.
        assert c.get("/api/v1/resources", params={"kind": "agent"}).status_code == 200
        # Nothing the refused delete touched: the folder is where it was.
        assert folder.is_dir()

        _switch(c, "knowledge", True)
        assert c.get(base).status_code == 200
        assert any(r["uid"] == uid for r in c.get("/api/v1/resources").json()["resources"])


def test_an_unknown_uid_is_still_not_found(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("knowledge", False)
    with _client() as c:
        r = c.get("/api/v1/resources/no-such-uid")
    assert r.status_code == 404
    assert r.json()["error"]["code"] != "FEATURE_DISABLED"


# --- what agents are told -------------------------------------------------------


def _instructions(c: TestClient) -> str:
    r = c.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS},
        headers=gates._HEADERS,
    )
    assert r.status_code == 200, r.text
    result: dict[str, Any] = r.json()["result"]
    return str(result["instructions"])


def _named_tools(text: str) -> set[str]:
    return set(re.findall(r"coffer__[a-z_]+", text))


def _listed_tools(c: TestClient) -> set[str]:
    session = gates._mcp(c, None, "initialize", INIT_PARAMS).headers["mcp-session-id"]
    return gates._tool_names(c, session)


def _guide(home: pathlib.Path) -> str:
    return (home / ".coffer" / "derived" / "skills" / GUIDE_SKILL_NAME / "SKILL.md").read_text()


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="agents are told only about the tools they have",
)
def test_agents_are_told_only_about_the_tools_they_have(home: pathlib.Path, fake_tool: str) -> None:
    with _client() as c:
        for enabled in (True, False):
            _switch(c, FAKE_FEATURE, enabled)
            listed = _listed_tools(c)
            assert (fake_tool in listed) is enabled
            assert _named_tools(_instructions(c)) <= listed


def test_agents_are_told_about_the_tool_and_the_knowledge_root(home: pathlib.Path) -> None:
    with _client() as c:
        text = _instructions(c)
        guide = _guide(home)
    for told in (text, guide):
        assert "coffer__search_tools" in told
        for retired in ("coffer__write", "coffer__recall", "coffer__diagnose"):
            assert retired not in told
        # Memory reaches an agent through its own native memory, not a path.
        assert "derived/memory" not in told
        assert "coffer log" in told
        assert "coffer path logs" in told
    assert "<!--" not in guide
    assert "~/.coffer/vault/knowledge" in guide
