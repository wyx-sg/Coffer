"""Custom-tool groups on REST (spec mcp-gateway).

Validation, Test, the health-ordered list,
against a real daemon and a fake HTTP API.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest

from tests.support.boundary_daemon import (
    BoundaryDaemon,
    prepare_home,
    running_daemon,
)
from tests.support.custom_tools import (
    SECRET_NAME,
    SECRET_VALUE,
    Agent,
    create_group,
    get_group,
    invocations,
    tool,
)
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


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool naming an undeclared argument is refused"
)
def test_a_tool_naming_an_undeclared_argument_is_refused(daemon: BoundaryDaemon, api: FakeHttpApi):
    create_group(daemon, "billing", api.base_url, [], secret=False)
    bad = {"name": "get", "method": "GET", "path": "/invoices/{id}"}
    r = daemon.client.post("/api/v1/custom-tools/billing/tools", json=bad)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CONFIG_INVALID"
    assert "'id'" in r.json()["error"]["message"]
    assert get_group(daemon, "billing")["tools"] == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a test runs a draft tool once without saving it"
)
def test_a_test_runs_a_draft_tool_once_without_saving_it(daemon: BoundaryDaemon, api: FakeHttpApi):
    group = create_group(daemon, "billing", api.base_url, [tool("keep", "GET", "/keep")])
    draft = tool("health", "GET", "/services/{service}/health")
    r = daemon.client.post(
        "/api/v1/custom-tools/billing/test", json={"tool": draft, "arguments": {"service": "web"}}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["status"] == 200
    assert out["status_line"] == "HTTP 200 OK"
    assert '"ok": true' in out["body"]
    assert api.seen[-1].path == "/services/web/health"
    assert SECRET_VALUE not in json.dumps(out)
    assert [t["name"] for t in get_group(daemon, "billing")["tools"]] == ["keep"]
    assert invocations(daemon, group["uid"], expect=1, timeout=0.5) == []


@pytest.mark.acceptance(spec="mcp-gateway", scenario="the group list puts a failing group first")
@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a failing group carries a hand-off prompt and a healthy one does not",
)
def test_the_group_list_puts_a_failing_group_first(daemon: BoundaryDaemon, api: FakeHttpApi):
    create_group(daemon, "a-good", api.base_url, [tool("ok", "GET", "/fine")], secret=False)
    create_group(daemon, "b-bad", api.base_url, [tool("broken", "GET", "/missing")], secret=False)
    off = create_group(daemon, "c-off", api.base_url, [tool("x", "GET", "/x")], secret=False)
    assert daemon.client.post(f"/api/v1/resources/{off['uid']}/disable").status_code == 200
    agent = Agent(daemon, "d" * 32)
    agent.call("a-good__ok")
    agent.call("b-bad__broken")
    invocations(daemon, get_group(daemon, "b-bad")["uid"], expect=1)
    invocations(daemon, get_group(daemon, "a-good")["uid"], expect=1)
    groups = daemon.client.get("/api/v1/custom-tools").json()["groups"]
    assert [(g["name"], g["health"]) for g in groups] == [
        ("b-bad", "failing"),
        ("a-good", "healthy"),
        ("c-off", "off"),
    ]
    assert groups[0]["failures_24h"] == 1
    # The failing group hands its diagnosis to an agent; a healthy or off one does not.
    assert "b-bad" in groups[0]["handoff"]["prompt"]
    assert groups[1]["handoff"] is None and groups[2]["handoff"] is None


def test_deleting_a_group_keeps_its_secret(daemon: BoundaryDaemon, api: FakeHttpApi):
    create_group(daemon, "billing", api.base_url, [tool("a", "GET", "/a")])
    assert daemon.client.delete("/api/v1/custom-tools/billing").status_code == 204
    assert daemon.value(f"secret/{SECRET_NAME}") == SECRET_VALUE


def test_an_http_mcp_server_is_not_a_custom_tool_group(daemon: BoundaryDaemon):
    config = {"transport": {"type": "http", "url": "https://mcp.example/mcp"}}
    r = daemon.client.post(
        "/api/v1/resources", json={"kind": "mcp_server", "name": "remote", "config": config}
    )
    assert r.status_code == 201, r.text
    assert daemon.client.get("/api/v1/custom-tools/remote").json()["error"]["code"] == (
        "NOT_A_CUSTOM_TOOL_GROUP"
    )
    assert daemon.client.get("/api/v1/custom-tools").json()["groups"] == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a group's headers are rows whose value is plain or a secret"
)
def test_a_groups_headers_are_rows_whose_value_is_plain_or_a_secret(
    daemon: BoundaryDaemon, api: FakeHttpApi
):
    daemon.store(f"secret/{SECRET_NAME}", SECRET_VALUE)
    r = daemon.client.post(
        "/api/v1/custom-tools",
        json={
            "name": "billing",
            "base_url": api.base_url,
            "headers": [
                {"name": "X-Team", "value": "billing"},
                {"name": "Authorization", "secret": SECRET_NAME, "scheme": "Bearer"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    group = r.json()
    rows = {h["name"]: h for h in group["headers"]}
    assert rows["X-Team"] == {
        "name": "X-Team", "value": "billing", "secret": None, "scheme": None,
        "secret_state": "none",
    }  # fmt: skip
    assert rows["Authorization"]["secret"] == SECRET_NAME
    assert rows["Authorization"]["scheme"] == "Bearer"
    assert rows["Authorization"]["value"] is None
    assert rows["Authorization"]["secret_state"] == "pending_approval"
    assert group["pending_secrets"] == [SECRET_NAME]
    assert SECRET_VALUE not in json.dumps(group)
    both = daemon.client.patch(
        "/api/v1/custom-tools/billing",
        json={"headers": [{"name": "A", "value": "x", "secret": SECRET_NAME}]},
    )
    assert both.status_code == 422
    replaced = daemon.client.patch(
        "/api/v1/custom-tools/billing", json={"headers": [{"name": "X-Team", "value": "ops"}]}
    )
    assert [h["name"] for h in replaced.json()["headers"]] == ["X-Team"]
    assert replaced.json()["secret_state"] == "none"
