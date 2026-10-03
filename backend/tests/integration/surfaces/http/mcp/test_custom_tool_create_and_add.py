"""Create a custom-tool group, add a tool and test it over REST (spec mcp-gateway
"Manage custom tools through REST and the Custom tools page")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.custom_tools import SECRET_NAME, SECRET_VALUE, get_group, tool
from tests.support.fake_http_api import FakeHttpApi, fake_http_api


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


@pytest.mark.acceptance(spec="mcp-gateway", scenario="create a custom-tool group and add a tool")
def test_create_a_group_and_add_a_tool(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    daemon.store(f"secret/{SECRET_NAME}", SECRET_VALUE)
    created = daemon.client.post(
        "/api/v1/custom-tools",
        json={
            "name": "deploy",
            "base_url": api.base_url + "/v1",
            "tools": [],
            "auth": {"header": "Authorization", "prefix": "Bearer ", "secret": SECRET_NAME},
        },
    )
    assert created.status_code == 201, created.text
    for approval_id in created.json()["pending_approvals"]:
        daemon.approve(approval_id)

    rollback = tool("rollback", "POST", "/services/{service}/rollback")
    rollback["input_schema"]["required"] = ["service"]
    added = daemon.client.post("/api/v1/custom-tools/deploy/tools", json=rollback)
    assert added.status_code in (200, 201), added.text

    [listed] = get_group(daemon, "deploy")["tools"]
    assert listed["name"] == "rollback" and listed["changes_data"] is True

    tested = daemon.client.post(
        "/api/v1/custom-tools/deploy/test", json={"tool": rollback, "arguments": {"service": "web"}}
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["status_line"] == "HTTP 200 OK"
    assert api.seen[-1].method == "POST" and api.seen[-1].path == "/v1/services/web/rollback"
