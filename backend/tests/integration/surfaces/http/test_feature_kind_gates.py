"""What a switched-off feature closes beyond its own routes, through the real daemon.

Spec experimental-features "Close every surface of a switched-off feature" and
"Withdraw what a switched-off feature put in front of agents": a feature's
resources are out of reach of the kind-agnostic resource routes, and the two
texts every agent is handed — the handshake instructions and the
``coffer-guide`` skill — name only the tools the tool list carries.

Boots ``create_app`` under a throwaway HOME, with the fixture and helpers of
``test_feature_gates``.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.daemon import config as daemon_config
from tests.integration.surfaces.http import test_feature_gates as gates

home = gates.home
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
        folder = home / "knowledge" / "research"
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
        # Nothing the refused delete touched: the folder is where it was.
        assert folder.is_dir()

        _switch(c, "knowledge", True)
        assert c.get(base).status_code == 200
        assert any(r["uid"] == uid for r in c.get("/api/v1/resources").json()["resources"])


def test_memory_off_closes_the_memory_kind_on_the_resource_routes(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("memory", False)
    with _client() as c:
        _assert_disabled(c.get("/api/v1/resources", params={"kind": "memory"}), "memory")
        assert all(r["kind"] != "memory" for r in c.get("/api/v1/resources").json()["resources"])
        # A kind no feature owns is untouched by the switch.
        assert c.get("/api/v1/resources", params={"kind": "agent"}).status_code == 200


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
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers=gates._HEADERS,
    )
    assert r.status_code == 200, r.text
    result: dict[str, Any] = r.json()["result"]
    return str(result["instructions"])


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="agents are told only about the tools they have",
)
def test_agents_are_told_only_about_the_tools_they_have(home: pathlib.Path) -> None:
    daemon_config.write_feature_setting("knowledge", False)
    daemon_config.write_feature_setting("memory", False)
    with _client() as c:
        text = _instructions(c)
        assert "coffer__write" not in text
        assert "coffer__recall" not in text
        assert "coffer__search_tools" in text
        guide = gates._guide(home)
        assert "coffer__write" not in guide
        assert "coffer__recall" not in guide
        assert "~/.coffer/knowledge" not in guide
        assert str(home / "knowledge") not in guide
        assert "<!--" not in guide

        _switch(c, "memory", True)
        assert "coffer__recall" in gates._guide(home)
        assert "coffer__write" not in gates._guide(home)
        assert "coffer__recall" in _instructions(c)
        assert "coffer__write" not in _instructions(c)


def test_with_every_feature_on_agents_are_told_about_every_tool(home: pathlib.Path) -> None:
    with _client() as c:
        text = _instructions(c)
        guide = gates._guide(home)
    for tool in ("coffer__write", "coffer__recall", "coffer__diagnose", "coffer__search_tools"):
        assert tool in text
        assert tool in guide
