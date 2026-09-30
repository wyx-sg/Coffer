"""Custom-tool groups on REST and the command line (spec mcp-gateway).

Validation, OpenAPI import and re-import, Test, the health-ordered list and
the ``coffer tool`` commands, against a real daemon and a fake HTTP API.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.infrastructure.mcp.tool_reach_repo import tool_reach_path
from coffer.surfaces.cli.main import app as cli_app
from tests.support.boundary_daemon import (
    BoundaryDaemon,
    point_cli_at,
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

_runner = CliRunner()


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
    assert (reading["auth_header"], reading["auth_prefix"]) == ("Authorization", "Bearer ")
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
            "/api/v1/custom-tools/billing/tools/list_charges/reach", json={"agents": [agent_uid]}
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


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the command line creates a group and adds a tool"
)
def test_the_command_line_creates_a_group_and_adds_a_tool(
    daemon: BoundaryDaemon, api: FakeHttpApi, monkeypatch: pytest.MonkeyPatch
):
    point_cli_at(daemon, monkeypatch)
    daemon.store(f"secret/{SECRET_NAME}", SECRET_VALUE)
    added = _runner.invoke(
        cli_app,
        [
            "tool", "add", "deploy", "--base-url", api.base_url + "/v1",
            "--auth-header", "Authorization", "--auth-prefix", "Bearer ", "--secret", SECRET_NAME,
        ],
    )  # fmt: skip
    assert added.exit_code == 9, added.output
    assert "waiting for approval in the Coffer app" in added.output
    for approval_id in get_group(daemon, "deploy")["pending_approvals"]:
        daemon.approve(approval_id)
    op = _runner.invoke(
        cli_app,
        [
            "tool", "op", "add", "deploy", "rollback", "--method", "POST",
            "--path", "/services/{service}/rollback", "--arg", "service:string:required",
        ],
    )  # fmt: skip
    assert op.exit_code == 0, op.output
    shown = _runner.invoke(cli_app, ["tool", "show", "deploy", "--json"])
    assert shown.exit_code == 0, shown.output
    [rollback] = json.loads(shown.output)["tools"]
    assert rollback["name"] == "rollback" and rollback["changes_data"] is True
    tested = _runner.invoke(
        cli_app, ["tool", "op", "test", "deploy", "rollback", "--arg-value", "service=web"]
    )
    assert tested.exit_code == 0, tested.output
    assert "HTTP 200 OK" in tested.output
    assert api.seen[-1].method == "POST" and api.seen[-1].path == "/v1/services/web/rollback"
    listed = _runner.invoke(cli_app, ["tool", "list", "--json"])
    assert [g["name"] for g in json.loads(listed.output)["groups"]] == ["deploy"]


def test_deleting_a_group_keeps_its_secret_and_drops_its_overrides(
    daemon: BoundaryDaemon, api: FakeHttpApi
):
    create_group(daemon, "billing", api.base_url, [tool("a", "GET", "/a")])
    daemon.client.put("/api/v1/custom-tools/billing/tools/a/reach", json={"agents": ["e" * 32]})
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
