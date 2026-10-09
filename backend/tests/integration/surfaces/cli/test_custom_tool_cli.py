"""``coffer custom-tool`` against a real in-process daemon.

Spec mcp-gateway "Manage custom tools from the command line": an agent sets a
group up one command at a time, the page's view of it is the same, a change made
on the page reads back on the command line, and an OpenAPI document is imported
and re-imported — every command a client of the daemon's own routes.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli.main import app
from tests.support.boundary_daemon import (
    BoundaryDaemon,
    point_cli_at,
    prepare_home,
    running_daemon,
)
from tests.support.fake_http_api import FakeHttpApi, fake_http_api

_runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        point_cli_at(d, monkeypatch)
        yield d


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


def coffer(*args: str, code: int = 0) -> Any:
    result = _runner.invoke(app, list(args))
    assert result.exit_code == code, (args, result.output)
    return result


def as_json(*args: str, code: int = 0) -> Any:
    return json.loads(coffer(*args, "--json", code=code).stdout)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a group is configured end to end from the command line"
)
def test_a_group_is_configured_end_to_end_from_the_command_line(
    daemon: BoundaryDaemon, api: FakeHttpApi, tmp_path: pathlib.Path
) -> None:
    daemon.store("secret/billing-test-token", "tok-test")
    coffer("custom-tool", "group", "create", "billing", "--env", f"test={api.base_url}/t")
    coffer("custom-tool", "env", "add", "billing", "live", "--base-url", f"{api.base_url}/l")
    pending = coffer(
        "custom-tool", "env", "set-header", "billing", "test", "Authorization",
        "--secret", "billing-test-token", "--scheme", "Bearer",
        code=9,
    )  # fmt: skip
    group = daemon.client.get("/api/v1/custom-tools/billing").json()
    [approval] = group["pending_approvals"]
    assert f"next: coffer approval approve {approval}" in pending.output
    daemon.approve(approval)
    search = tmp_path / "search.json"
    search.write_text(
        json.dumps(
            {
                "name": "search",
                "method": "POST",
                "path": "/search",
                "changes_data": False,
                "input_schema": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                    "required": ["q"],
                },
            }
        )
    )
    coffer("custom-tool", "tool", "add", "billing", "--data", f"@{search}")
    coffer("custom-tool", "group", "reach", "billing", "--all")
    result = as_json(
        "custom-tool", "tool", "test", "billing", "search", "--env", "test", "--args", '{"q":"x"}'
    )
    assert result["status_line"] == "HTTP 200 OK" and result["environment"] == "test"
    assert result["url"] == f"{api.base_url}/t/search"
    assert api.seen[-1].headers["authorization"] == "Bearer tok-test"
    # What the page reads is what the commands made.
    page = daemon.client.get("/api/v1/custom-tools/billing").json()
    assert [e["name"] for e in page["environments"]] == ["test", "live"]
    assert page["environments"][0]["headers"][0]["secret"] == "billing-test-token"
    [tool] = page["tools"]
    assert tool["name"] == "search" and tool["changes_data"] is False
    assert page["scope"] is None
    # Arguments the schema refuses never leave Coffer.
    seen = len(api.seen)
    bad = json.loads(
        coffer(
            "custom-tool", "tool", "test", "billing", "search", "--env", "test",
            "--args", '{"q": 1}', "--json",
            code=6,
        ).stderr
    )  # fmt: skip
    assert bad["error"]["code"] == "CUSTOM_TOOL_ARGUMENTS_INVALID"
    assert bad["error"]["details"]["errors"][0]["path"] == "/q"
    assert len(api.seen) == seen


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a dry run on the command line prints the request and sends nothing",
)
def test_a_dry_run_prints_the_request_and_sends_nothing(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    daemon.store("secret/billing-test-token", "tok-test")
    coffer("custom-tool", "group", "create", "billing", "--env", f"test={api.base_url}/t")
    coffer("custom-tool", "env", "add", "billing", "live", "--base-url", f"{api.base_url}/l")
    coffer(
        "custom-tool", "env", "set-header", "billing", "test", "Authorization",
        "--secret", "billing-test-token", "--scheme", "Bearer",
        code=9,
    )  # fmt: skip
    coffer(
        "custom-tool", "tool", "add", "billing", "--name", "status", "--method", "GET",
        "--path", "/status", "--header", "X-Client=coffer",
    )  # fmt: skip
    preview = as_json(
        "custom-tool", "tool", "test", "billing", "status", "--env", "test", "--dry-run"
    )
    assert preview["url"] == f"{api.base_url}/t/status" and preview["environment"] == "test"
    auth = next(h for h in preview["headers"] if h["name"] == "Authorization")
    assert auth["value"] == "Bearer ***"
    assert auth["secret"]["name"] == "billing-test-token"
    assert auth["secret"]["state"] == "pending_approval"
    human = coffer("custom-tool", "tool", "test", "billing", "status", "--env", "live", "--dry-run")
    assert f"GET {api.base_url}/l/status  [live]" in human.stdout
    assert "X-Client: coffer" in human.stdout and "nothing was sent" in human.stdout
    assert "tok-test" not in human.stdout + json.dumps(preview)
    # A secret made under a label is named by it.
    minted = _runner.invoke(app, ["secret", "set", "--name", "billing live key"], input="tok-live")
    ref = minted.stdout.split("stored: ", 1)[1].split()[0]
    coffer(
        "custom-tool", "env", "set-header", "billing", "live", "X-Api-Key",
        "--secret", ref.removeprefix("secret/"),
        code=9,
    )  # fmt: skip
    live = as_json("custom-tool", "tool", "test", "billing", "status", "--env", "live", "--dry-run")
    key = next(h for h in live["headers"] if h["name"] == "X-Api-Key")
    assert key["value"] == "***" and key["secret"]["name"] == "billing live key"
    assert key["secret"]["id"] == ref and "tok-live" not in json.dumps(live)
    needs_env = json.loads(
        coffer(
            "custom-tool", "tool", "test", "billing", "status", "--dry-run", "--json", code=6
        ).stderr
    )
    assert needs_env["error"]["code"] == "CUSTOM_TOOL_ENVIRONMENT_REQUIRED"
    draft = as_json(
        "custom-tool", "tool", "test-draft", "billing", "--env", "live", "--dry-run",
        "--data", '{"name": "probe", "method": "GET", "path": "/probe"}',
    )  # fmt: skip
    assert draft["url"] == f"{api.base_url}/l/probe"
    assert api.seen == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a change made on the page is read back by the command line"
)
def test_a_change_made_on_the_page_reads_back(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    coffer("custom-tool", "group", "create", "billing", "--env", f"staging={api.base_url}")
    coffer(
        "custom-tool", "tool", "add", "billing", "--name", "ping", "--method", "GET",
        "--path", "/ping",
    )  # fmt: skip
    # The page renames the environment and switches the tool off.
    base = "/api/v1/custom-tools/billing"
    assert daemon.client.patch(f"{base}/environments/staging", json={"name": "uat"}).is_success
    assert daemon.client.patch(f"{base}/tools/ping", json={"enabled": False}).is_success
    group = as_json("custom-tool", "group", "show", "billing")
    assert [e["name"] for e in group["environments"]] == ["uat"]
    assert group["tools"][0]["enabled"] is False
    listed = coffer("custom-tool", "group", "list").stdout
    assert "billing" in listed and "uat" in listed


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="an OpenAPI document is imported and re-imported from the command line",
)
def test_an_openapi_document_is_imported_and_reimported(
    daemon: BoundaryDaemon, api: FakeHttpApi, tmp_path: pathlib.Path
) -> None:
    def spec(*ops: str) -> dict[str, Any]:
        return {
            "openapi": "3.1.0",
            "info": {"title": "Billing", "version": "1"},
            "servers": [{"url": api.base_url}],
            "paths": {f"/{op}": {"get": {"operationId": op}} for op in ops},
        }

    doc = tmp_path / "openapi.json"
    doc.write_text(json.dumps(spec("a", "b", "c")))
    reading = as_json("custom-tool", "import", "read", "--file", str(doc))
    assert [op["key"] for op in reading["operations"]] == ["GET /a", "GET /b", "GET /c"]
    created = as_json(
        "custom-tool", "group", "create", "billing", "--from-openapi", str(doc),
        "--operation", "GET /a", "--operation", "GET /b",
        "--env", f"test={api.base_url}", "--env", f"live={api.base_url}/l",
    )  # fmt: skip
    assert [t["name"] for t in created["tools"]] == ["a", "b"]
    doc.write_text(json.dumps(spec("a", "b", "c", "d")))
    preview = as_json("custom-tool", "reimport", "preview", "billing", "--file", str(doc))
    assert [op["key"] for op in preview["added"]] == ["GET /d"]
    assert daemon.client.get("/api/v1/custom-tools/billing").json()["tools"] == created["tools"]
    applied = as_json(
        "custom-tool", "reimport", "apply", "billing", "--file", str(doc), "--add", "GET /d"
    )
    assert [t["name"] for t in applied["tools"]] == ["a", "b", "d"]
    assert [e["name"] for e in applied["environments"]] == ["test", "live"]


def test_every_custom_tool_group_renders_its_help() -> None:
    for path in ("group", "tool", "env", "import", "reimport"):
        assert "Usage" in coffer("custom-tool", path, "--help").output
