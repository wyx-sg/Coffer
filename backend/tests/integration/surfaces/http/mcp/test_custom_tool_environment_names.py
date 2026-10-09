"""Environment names in the management routes: spelling and reuse.

Spec mcp-gateway "Keep a custom-tool group's environments in the group".
Environment names are unique in a group regardless of case, so a change or a
delete that names an environment in another case reaches that environment —
it is never answered 200 with nothing changed. A name renamed away and added
again gets a fresh binding key, whatever its length.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from typing import Any

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.custom_tools import Agent
from tests.support.fake_http_api import FakeHttpApi, fake_http_api

BASE = "/api/v1/custom-tools/billing/environments"
CLAUDE = "a" * 32

pytestmark = pytest.mark.timeout(60)


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


def _group(d: BoundaryDaemon, envs: list[dict[str, Any]]) -> dict[str, Any]:
    r = d.client.post(
        "/api/v1/custom-tools",
        json={
            "name": "billing",
            "environments": envs,
            "tools": [{"name": "ping", "method": "GET", "path": "/ping"}],
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def _envs(d: BoundaryDaemon) -> list[dict[str, Any]]:
    r = d.client.get("/api/v1/custom-tools/billing")
    assert r.status_code == 200, r.text
    return list(r.json()["environments"])


def _stored_keys(d: BoundaryDaemon) -> list[str]:
    r = d.client.get("/api/v1/resources", params={"kind": "mcp_server", "name": "billing"})
    assert r.status_code == 200, r.text
    (resource,) = r.json()["resources"]
    return [e["key"] for e in resource["config"]["transport"]["environments"]]


def _selector_enum(d: BoundaryDaemon) -> list[str]:
    ping = Agent(d, CLAUDE).tools()["billing__ping"]
    return list(ping["inputSchema"]["properties"]["coffer_environment"]["enum"])


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an environment named in another case is changed or deleted"
)
def test_a_change_or_delete_in_another_case_reaches_the_environment(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(
        daemon,
        [
            {"name": "Test", "base_url": api.base_url + "/t"},
            {"name": "live", "base_url": api.base_url + "/l"},
        ],
    )

    r = daemon.client.patch(f"{BASE}/test", json={"description": "the sandbox"})
    assert r.status_code == 200, r.text
    test_env = next(e for e in _envs(daemon) if e["name"] == "Test")
    assert test_env["description"] == "the sandbox"

    # A case-only rename is a rename of that environment, not a clash with itself.
    r = daemon.client.patch(f"{BASE}/TEST", json={"name": "test"})
    assert r.status_code == 200, r.text
    assert sorted(e["name"] for e in _envs(daemon)) == ["live", "test"]
    assert sorted(_selector_enum(daemon)) == ["live", "test"]

    r = daemon.client.delete(f"{BASE}/TeSt")
    assert r.status_code == 200, r.text
    assert [e["name"] for e in _envs(daemon)] == ["live"]
    assert _selector_enum(daemon) == ["live"]


def test_an_unknown_name_in_any_case_is_404_and_changes_nothing(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(
        daemon,
        [
            {"name": "Test", "base_url": api.base_url + "/t"},
            {"name": "live", "base_url": api.base_url + "/l"},
        ],
    )
    before = _envs(daemon)
    assert daemon.client.patch(f"{BASE}/uat", json={"description": "x"}).status_code == 404
    assert daemon.client.delete(f"{BASE}/UAT").status_code == 404
    assert _envs(daemon) == before


def test_renaming_onto_another_environment_in_another_case_is_refused(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(
        daemon,
        [
            {"name": "Test", "base_url": api.base_url + "/t"},
            {"name": "live", "base_url": api.base_url + "/l"},
        ],
    )
    r = daemon.client.patch(f"{BASE}/live", json={"name": "TEST"})
    assert r.status_code == 409, r.text
    assert sorted(e["name"] for e in _envs(daemon)) == ["Test", "live"]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a 40-character environment name renamed and added again"
)
def test_a_40_character_name_renamed_and_added_again_gets_its_own_key(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    long_name = "e" * 40
    _group(daemon, [{"name": long_name, "base_url": api.base_url + "/a"}])
    assert daemon.client.patch(f"{BASE}/{long_name}", json={"name": "old"}).status_code == 200
    for _ in range(3):
        r = daemon.client.post(BASE, json={"name": long_name, "base_url": api.base_url + "/b"})
        assert r.status_code == 201, r.text
        renamed = f"old{_}"
        assert daemon.client.patch(f"{BASE}/{long_name}", json={"name": renamed}).status_code == 200
    r = daemon.client.post(BASE, json={"name": long_name, "base_url": api.base_url + "/c"})
    assert r.status_code == 201, r.text
    keys = _stored_keys(daemon)
    assert len(keys) == len(set(keys)) == 5
    assert all(0 < len(k) <= 40 for k in keys)
