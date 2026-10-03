"""Custom-tool groups on REST (spec mcp-gateway).

Validation, OpenAPI import and re-import, Test, the health-ordered list,
against a real daemon and a fake HTTP API.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest

from coffer.infrastructure.mcp.tool_reach_repo import tool_reach_path
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


def _document(*ops: tuple[str, str, str]) -> dict[str, Any]:
    """An OpenAPI 3.1 document with ``(method, path, operationId)`` operations."""
    paths: dict[str, Any] = {}
    for method, path, op_id in ops:
        paths.setdefault(path, {})[method.lower()] = {"operationId": op_id, "summary": op_id}
    return {
        "openapi": "3.1.0",
        "info": {"title": "Billing", "version": "2.3.0"},
        "servers": [{"url": "https://billing.example/v2"}],
        "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}}},
        "paths": paths,
    }


_FIVE = (
    ("GET", "/invoices", "listInvoices"),
    ("POST", "/invoices", "createInvoice"),
    ("GET", "/charges", "listCharges"),
    ("POST", "/charges/refund", "refundCharge"),
    ("DELETE", "/charges", "voidCharge"),
)


def _read(d: BoundaryDaemon, doc: dict[str, Any]) -> dict[str, Any]:
    r = d.client.post(
        "/api/v1/custom-tools/openapi", json={"document": json.dumps(doc), "filename": "b.json"}
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


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


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an OpenAPI document becomes draft tools")
def test_an_openapi_document_becomes_draft_tools(daemon: BoundaryDaemon):
    reading = _read(daemon, _document(*_FIVE))
    assert len(reading["operations"]) == 5
    assert reading["base_url"] == "https://billing.example/v2"
    assert reading["auth_header"] == "Authorization"
    by_key = {op["key"]: op["tool"] for op in reading["operations"]}
    assert by_key["GET /invoices"]["name"] == "list_invoices"
    picked = [by_key[k] for k in ("GET /invoices", "GET /charges", "POST /invoices")]
    skipped = sorted(set(by_key) - {"GET /invoices", "GET /charges", "POST /invoices"})
    r = daemon.client.post(
        "/api/v1/custom-tools",
        json={
            "name": "billing",
            "base_url": reading["base_url"],
            "tools": picked,
            "source": {"kind": "file", "location": "b.json", "skipped": skipped},
        },
    )
    assert r.status_code == 201, r.text
    group = r.json()
    assert sorted(t["name"] for t in group["tools"]) == [
        "create_invoice",
        "list_charges",
        "list_invoices",
    ]
    assert all(t["enabled"] for t in group["tools"])
    assert group["source"]["skipped"] == skipped


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an OpenAPI URL on a private address is refused"
)
def test_an_openapi_url_on_a_private_address_is_refused(daemon: BoundaryDaemon, api: FakeHttpApi):
    api.openapi = _document(*_FIVE)
    r = daemon.client.post(
        "/api/v1/custom-tools/openapi", json={"url": f"{api.base_url}/openapi.json"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "OPENAPI_UNREADABLE"
    assert "as a file" in r.json()["error"]["message"]
    assert api.seen == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="re-import applies additions and removals keeping switches"
)
@pytest.mark.acceptance(
    spec="web-ui", scenario="re-importing a spec previews the operations it adds and removes"
)
def test_reimport_applies_additions_and_removals_keeping_switches(daemon: BoundaryDaemon):
    three = _FIVE[:3]
    reading = _read(daemon, _document(*three))
    r = daemon.client.post(
        "/api/v1/custom-tools",
        json={
            "name": "billing",
            "base_url": "https://billing.example/v2",
            "tools": [op["tool"] for op in reading["operations"]],
            "source": {"kind": "file", "location": "b.json"},
        },
    )
    assert r.status_code == 201, r.text
    assert (
        daemon.client.patch(
            "/api/v1/custom-tools/billing/tools/create_invoice", json={"enabled": False}
        ).status_code
        == 200
    )
    agent_uid = "c" * 32
    assert (
        daemon.client.put(
            "/api/v1/custom-tools/billing/tools/list_charges/reach",
            json={"mode": "chosen", "agents": [agent_uid]},
        ).status_code
        == 200
    )
    # The new document drops GET /invoices and adds POST /charges/refund.
    changed = json.dumps(_document(*three[1:], _FIVE[3]))
    before = get_group(daemon, "billing")
    r = daemon.client.post(
        "/api/v1/custom-tools/billing/reimport/preview", json={"document": changed}
    )
    assert r.status_code == 200, r.text
    preview = r.json()
    assert [op["key"] for op in preview["added"]] == ["POST /charges/refund"]
    assert preview["removed"] == ["list_invoices"]
    assert get_group(daemon, "billing")["tools"] == before["tools"]
    r = daemon.client.post(
        "/api/v1/custom-tools/billing/reimport",
        json={"document": changed, "add": ["POST /charges/refund"]},
    )
    assert r.status_code == 200, r.text
    tools = {t["name"]: t for t in r.json()["tools"]}
    assert set(tools) == {"create_invoice", "list_charges", "refund_charge"}
    assert tools["refund_charge"]["enabled"] is True
    assert tools["create_invoice"]["enabled"] is False
    assert tools["list_charges"]["reach_override"] == [agent_uid]


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


def test_deleting_a_group_keeps_its_secret_and_drops_its_overrides(
    daemon: BoundaryDaemon, api: FakeHttpApi
):
    create_group(daemon, "billing", api.base_url, [tool("a", "GET", "/a")])
    daemon.client.put(
        "/api/v1/custom-tools/billing/tools/a/reach", json={"mode": "chosen", "agents": ["e" * 32]}
    )
    assert daemon.client.delete("/api/v1/custom-tools/billing").status_code == 204
    assert daemon.value(f"secret/{SECRET_NAME}") == SECRET_VALUE
    assert json.loads(tool_reach_path(daemon.home).read_text()) == {}


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


def _pretty(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the import preview shows each operation's source"
)
def test_the_import_preview_shows_each_operations_source(daemon: BoundaryDaemon):
    r = daemon.client.post(
        "/api/v1/custom-tools/openapi",
        json={"document": _pretty(_document(*_FIVE[:2])), "filename": "b.json"},
    )
    assert r.status_code == 200, r.text
    ops = {op["key"]: op for op in r.json()["operations"]}
    source = ops["GET /invoices"]["source"]
    assert source["start_line"] < source["end_line"]
    assert '"operationId": "listInvoices"' in source["text"]
    assert ops["GET /invoices"]["tool"]["source_text"] == source["text"]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a re-import preview shows an operation's old and new text"
)
def test_a_reimport_preview_shows_the_old_and_new_text_of_a_changed_operation(
    daemon: BoundaryDaemon,
):
    first = _document(("POST", "/invoices", "createInvoice"))
    reading = daemon.client.post(
        "/api/v1/custom-tools/openapi", json={"document": _pretty(first), "filename": "b.json"}
    ).json()
    created = daemon.client.post(
        "/api/v1/custom-tools",
        json={
            "name": "billing",
            "base_url": "https://billing.example/v2",
            "tools": [op["tool"] for op in reading["operations"]],
            "source": {"kind": "file", "location": "b.json"},
        },
    )
    assert created.status_code == 201, created.text
    second = _document(("POST", "/invoices", "createInvoice"))
    second["paths"]["/invoices"]["post"]["requestBody"] = {
        "required": True,
        "content": {"application/json": {"schema": {"type": "object", "required": ["currency"]}}},
    }
    r = daemon.client.post(
        "/api/v1/custom-tools/billing/reimport/preview", json={"document": _pretty(second)}
    )
    assert r.status_code == 200, r.text
    [change] = r.json()["changed"]
    assert change["operation"] == "POST /invoices"
    assert "requestBody" not in change["old_text"]
    assert '"currency"' in change["new_text"]
    assert change["new_start_line"] < change["new_end_line"]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a group's headers are rows whose value is plain or a whole secret"
)
def test_a_groups_headers_are_rows_whose_value_is_plain_or_a_whole_secret(
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
                {"name": "Authorization", "secret": SECRET_NAME},
            ],
        },
    )
    assert r.status_code == 201, r.text
    group = r.json()
    rows = {h["name"]: h for h in group["headers"]}
    assert rows["X-Team"] == {
        "name": "X-Team", "value": "billing", "secret": None, "secret_state": "none"
    }  # fmt: skip
    assert rows["Authorization"]["secret"] == SECRET_NAME
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


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an unreachable spec URL says why")
def test_an_unresolvable_spec_host_answers_unreachable_with_a_handoff(daemon: BoundaryDaemon):
    r = daemon.client.post(
        "/api/v1/custom-tools/openapi", json={"url": "https://no-such-host.invalid/openapi.json"}
    )
    assert r.status_code == 502, r.text
    error = r.json()["error"]
    assert error["code"] == "OPENAPI_UNREACHABLE"
    assert error["details"]["reason"] == "dns"
    assert "VPN" in error["details"]["handoff"]["prompt"]
