"""Custom tools through the real gateway (spec mcp-gateway).

A real daemon over a throwaway home, a fake HTTP API on 127.0.0.1, and agents
speaking JSON-RPC to ``/mcp``: every scenario here is what an agent sees and
what the upstream receives.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections.abc import Iterator

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.custom_tools import (
    SECRET_NAME,
    SECRET_VALUE,
    Agent,
    create_group,
    get_group,
    invocations,
    refusal,
    text_of,
    tool,
)
from tests.support.fake_http_api import FakeHttpApi, fake_http_api

_FAKE_MCP = pathlib.Path(__file__).resolve().parents[4] / "fixtures" / "fake_mcp_server.py"
CLAUDE = "a" * 32
CODEX = "b" * 32


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
    spec="mcp-gateway", scenario="a custom tool reaches the agent under its group's prefix"
)
@pytest.mark.acceptance(spec="web-ui", scenario="an agent sees the group name as the tool prefix")
def test_a_custom_tool_reaches_the_agent_under_its_prefix(daemon: BoundaryDaemon, api: FakeHttpApi):
    create_group(
        daemon,
        "billing",
        api.base_url,
        [tool("list_invoices", "GET", "/invoices", description="List invoices")],
    )
    listed = Agent(daemon, CLAUDE).tools()
    assert "billing__list_invoices" in listed
    entry = listed["billing__list_invoices"]
    assert entry["description"] == "List invoices"
    assert entry["inputSchema"]["type"] == "object"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a group's description finds its tools in a search"
)
def test_a_groups_description_finds_its_tools(daemon: BoundaryDaemon, api: FakeHttpApi):
    create_group(
        daemon,
        "acme",
        api.base_url,
        [tool("list_items", "GET", "/items", description="List items")],
        description="Weather forecasts for warehouse sites",
    )
    found = json.loads(
        text_of(Agent(daemon, CLAUDE).call("coffer__search_tools", {"query": "weather forecast"}))
    )
    assert found["tools"][0]["name"] == "acme__list_items"
    assert found["tools"][0]["group_description"] == "Weather forecasts for warehouse sites"
    # tools/list keeps the tool's own description.
    assert Agent(daemon, CLAUDE).tools()["acme__list_items"]["description"] == "List items"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a custom tool call sends the rendered request with the secret"
)
@pytest.mark.acceptance(spec="web-ui", scenario="the secret never reaches the agent")
def test_a_call_sends_the_rendered_request_with_the_secret(
    daemon: BoundaryDaemon, api: FakeHttpApi
):
    group = create_group(
        daemon,
        "billing",
        api.base_url + "/v2",
        [tool("get_invoice", "GET", "/invoices/{id}?status={status}")],
    )
    agent = Agent(daemon, CLAUDE)
    # What the agent is offered carries neither the value nor the reference.
    offered = json.dumps(agent.tools()["billing__get_invoice"])
    assert SECRET_VALUE not in offered and SECRET_NAME not in offered
    result = agent.call("billing__get_invoice", {"id": "a/b"})
    assert SECRET_VALUE not in json.dumps(result) and SECRET_NAME not in json.dumps(result)
    assert result["result"].get("isError") in (None, False)
    assert text_of(result).startswith("HTTP 200 OK")
    seen = api.seen[-1]
    assert (seen.method, seen.path) == ("GET", "/v2/invoices/a%2Fb")
    assert seen.headers["authorization"] == SECRET_VALUE
    rows = invocations(daemon, group["uid"], expect=1)
    assert [(r["capability_key"], r["status"]) for r in rows] == [("get_invoice", "ok")]
    assert "a/b" not in json.dumps(rows) and SECRET_VALUE not in json.dumps(rows)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a custom tool's response is capped and masked"
)
def test_a_response_is_capped_and_masked(daemon: BoundaryDaemon, api: FakeHttpApi):
    api.echo_secret = SECRET_VALUE
    create_group(daemon, "billing", api.base_url, [tool("big", "GET", "/big")])
    text = text_of(Agent(daemon, CLAUDE).call("billing__big"))
    assert len(text.encode()) < 1024 * 1024 + 200
    assert "[response cut at 1048576 bytes]" in text
    assert SECRET_VALUE not in text and "***" in text


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an error status is an error result and a redirect is not followed"
)
def test_an_error_status_is_an_error_and_a_redirect_is_not_followed(
    daemon: BoundaryDaemon, api: FakeHttpApi
):
    group = create_group(
        daemon,
        "billing",
        api.base_url,
        [tool("gone", "GET", "/missing"), tool("moved", "GET", "/redirect")],
    )
    agent = Agent(daemon, CLAUDE)
    missing = agent.call("billing__gone")
    assert missing["result"]["isError"] is True
    assert text_of(missing).startswith("HTTP 404")
    moved = agent.call("billing__moved")
    assert "HTTP 302" in text_of(moved)
    assert f"Location: {api.redirect_to} (not followed)" in text_of(moved)
    assert [s.path for s in api.seen] == ["/missing", "/redirect"]
    statuses = {
        r["capability_key"]: r["status"] for r in invocations(daemon, group["uid"], expect=2)
    }
    assert statuses["gone"] == "error"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a custom tool that changes data is annotated destructive"
)
@pytest.mark.acceptance(
    spec="web-ui", scenario="a tool that changes data is annotated for the agent"
)
def test_a_tool_that_changes_data_is_annotated(daemon: BoundaryDaemon, api: FakeHttpApi):
    create_group(
        daemon,
        "billing",
        api.base_url,
        [
            tool("invoices", "GET", "/invoices"),
            tool("refunds", "POST", "/refunds"),
            tool("search", "POST", "/search", changes_data=False),
        ],
    )
    listed = Agent(daemon, CLAUDE).tools()
    assert listed["billing__refunds"]["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": True,
    }
    assert listed["billing__invoices"]["annotations"] == {"readOnlyHint": True}
    assert listed["billing__search"]["annotations"] == {"readOnlyHint": True}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an upstream tool's own annotations reach the agent"
)
def test_an_upstream_tools_annotations_reach_the_agent(daemon: BoundaryDaemon):
    config = {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE_MCP), "--tools", "peek", "poke", "--read-only-tools", "peek"],
        }
    }
    r = daemon.client.post(
        "/api/v1/resources", json={"kind": "mcp_server", "name": "fs", "config": config}
    )
    assert r.status_code == 201, r.text
    listed = Agent(daemon, CLAUDE).tools()
    assert listed["fs__peek"]["annotations"] == {"readOnlyHint": True}
    assert "annotations" not in listed["fs__poke"]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a switched-off custom tool is hidden and refused"
)
def test_a_switched_off_tool_is_hidden_and_refused(daemon: BoundaryDaemon, api: FakeHttpApi):
    group = create_group(
        daemon,
        "billing",
        api.base_url,
        [tool("on", "GET", "/on"), tool("off", "GET", "/off", enabled=False)],
    )
    agent = Agent(daemon, CLAUDE)
    assert {"billing__on"} == {n for n in agent.tools() if n.startswith("billing__")}
    refused = agent.call("billing__off")
    assert refused["error"]["code"] == -32000
    assert api.seen == []
    rows = invocations(daemon, group["uid"], expect=1)
    assert [(r["capability_key"], r["status"]) for r in rows] == [("off", "denied")]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="every tool that is on follows its group's reach"
)
def test_every_tool_that_is_on_follows_its_groups_reach(daemon: BoundaryDaemon, api: FakeHttpApi):
    create_group(
        daemon,
        "billing",
        api.base_url,
        [tool("list_invoices", "GET", "/invoices"), tool("refund", "POST", "/refunds")],
        agents=[CLAUDE],
    )
    seen = lambda a: {n for n in Agent(daemon, a).tools() if n.startswith("billing__")}  # noqa: E731
    assert seen(CLAUDE) == {"billing__list_invoices", "billing__refund"}
    assert seen(CODEX) == set()


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="binding a stored secret to a group waits for approval"
)
def test_binding_a_stored_secret_waits_for_approval(daemon: BoundaryDaemon, api: FakeHttpApi):
    group = create_group(
        daemon, "billing", api.base_url, [tool("list_invoices", "GET", "/invoices")], approve=False
    )
    assert group["secret_state"] == "pending_approval"
    assert len(group["pending_approvals"]) == 1
    [pending] = daemon.pending(destination_uid=group["uid"])
    assert pending["target"] == f"http_api {api.base_url}/"
    failed = refusal(Agent(daemon, CLAUDE).call("billing__list_invoices"))
    assert "SECRET_BINDING_PENDING" in failed and "waiting for approval" in failed
    assert f"coffer approval approve {group['pending_approvals'][0]}" in failed
    assert api.seen == []
    daemon.approve(group["pending_approvals"][0])
    assert get_group(daemon, "billing")["secret_state"] == "present"
    Agent(daemon, CLAUDE).call("billing__list_invoices")
    assert api.seen[-1].headers["authorization"] == SECRET_VALUE


@pytest.mark.acceptance(spec="mcp-gateway", scenario="moving a group's base URL asks again")
def test_moving_the_base_url_asks_again(daemon: BoundaryDaemon, api: FakeHttpApi):
    create_group(daemon, "billing", api.base_url, [tool("list_invoices", "GET", "/invoices")])
    r = daemon.client.patch("/api/v1/custom-tools/billing", json={"base_url": api.base_url + "/v3"})
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["secret_state"] == "pending_approval"
    failed = refusal(Agent(daemon, CLAUDE).call("billing__list_invoices"))
    assert "SECRET_BINDING_PENDING" in failed and "waiting for approval" in failed
    assert api.seen == []
    [pending] = daemon.pending(destination_uid=moved["uid"])
    assert pending["target"] == f"http_api {api.base_url}/v3"


def _set_exposure(daemon: BoundaryDaemon, uid: str, tool_name: str, mode: str) -> None:
    r = daemon.client.patch(
        f"/api/v1/resources/mcp_server/{uid}/tools/{tool_name}/exposure", json={"mode": mode}
    )
    assert r.status_code == 204, r.text


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a custom tool's exposure is honoured like any server's tool"
)
def test_a_custom_tools_exposure_is_honoured_by_the_gateway(
    daemon: BoundaryDaemon, api: FakeHttpApi, monkeypatch: pytest.MonkeyPatch
):
    group = create_group(
        daemon,
        "billing",
        api.base_url,
        [
            tool("list_invoices", "GET", "/invoices", description="List every invoice"),
            tool("get_invoice", "GET", "/invoices/{id}"),
            tool("void_invoice", "POST", "/invoices/{id}/void"),
        ],
    )
    # No agent has listed the group yet: its tools are its config.
    _set_exposure(daemon, group["uid"], "list_invoices", "search")
    agent = Agent(daemon, CLAUDE)
    listed = agent.tools()
    assert "billing__list_invoices" not in listed
    assert {"billing__get_invoice", "billing__void_invoice"} <= set(listed)

    # Search only: coffer__search_tools still finds it, and it can still be called.
    found = text_of(agent.call("coffer__search_tools", {"query": "list every invoice"}))
    assert json.loads(found)["tools"][0]["name"] == "billing__list_invoices"
    assert text_of(agent.call("billing__list_invoices")).startswith("HTTP 200")

    # Always listed survives a budget too small for the rest of the group.
    monkeypatch.setenv("COFFER_TOOL_TIERING_BUDGET", "1")
    _set_exposure(daemon, group["uid"], "void_invoice", "listed")
    narrow = {n for n in Agent(daemon, CLAUDE).tools() if n.startswith("billing__")}
    assert narrow == {"billing__void_invoice"}

    tiering = daemon.client.get(f"/api/v1/resources/mcp_server/{group['uid']}/tiering").json()
    modes = {t["tool"]: (t["mode"], t["effective"]) for t in tiering["tools"]}
    assert modes == {
        "list_invoices": ("search", "search"),
        "get_invoice": ("auto", "search"),
        "void_invoice": ("listed", "listed"),
    }
