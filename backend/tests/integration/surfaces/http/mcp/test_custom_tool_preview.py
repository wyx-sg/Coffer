"""A custom tool's request preview (dry run) and a test's diagnostic headers, against a real daemon.

Spec mcp-gateway "Preview a custom tool's request without sending it" and
"Report what a custom tool's test reached". The upstream is a real socket that
records every request it receives, so "nothing was sent" is observed, not assumed.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from coffer.application.secret.resolver import SecretResolver
from coffer.surfaces.http.secret_composition import get_secret_store
from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.fake_http_api import FakeHttpApi, fake_http_api

TEST_TOKEN, LIVE_TOKEN = "tok-test-1111", "tok-live-2222"
_GROUPS = "/api/v1/custom-tools"


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


_SEARCH = {
    "name": "search",
    "method": "POST",
    "path": "/v1/{env:region}/search?cid={cid}",
    "headers": {"X-Client": "coffer-{env:region}"},
    "body_template": '{"query": {q}}',
    "changes_data": False,
    "input_schema": {
        "type": "object",
        "properties": {"q": {"type": "string"}, "cid": {"type": "string"}},
        "required": ["q", "cid"],
    },
}


def _env(name: str, url: str, secret: str, **extra: Any) -> dict[str, Any]:
    headers = [
        {"name": "Authorization", "secret": secret, "scheme": "Bearer"},
        {"name": "X-Tenant", "value": f"tenant-{name}"},
    ]
    return {"name": name, "base_url": url, "headers": headers, **extra}


def _two_envs(d: BoundaryDaemon, api: FakeHttpApi) -> None:
    d.store("secret/test-key", TEST_TOKEN)
    d.store("secret/live-key", LIVE_TOKEN)
    body = {
        "name": "billing",
        "timeout_seconds": 30,
        "environments": [
            _env("test", api.base_url + "/t", "test-key", variables={"region": "eu-1"}),
            _env(
                "live",
                api.base_url + "/l",
                "live-key",
                variables={"region": "us-1"},
                timeout_seconds=7,
            ),
        ],
        "tools": [_SEARCH],
    }
    r = d.client.post(_GROUPS, json=body)
    assert r.status_code == 201, r.text
    for approval_id in r.json()["pending_approvals"]:
        d.approve(approval_id)


@pytest.fixture
def nothing_leaves(monkeypatch: pytest.MonkeyPatch) -> None:
    """A preview that reached for a secret value or the network fails loudly."""

    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("a preview must not read a secret value or send a request")

    monkeypatch.setattr(SecretResolver, "materialize", refuse)
    monkeypatch.setattr(SecretResolver, "materialize_async", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


def _preview(d: BoundaryDaemon, env: str | None, args: dict[str, Any]) -> httpx.Response:
    return d.client.post(
        f"{_GROUPS}/billing/tools/search/preview", json={"arguments": args, "environment": env}
    )


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a dry run shows each environment's request without sending it"
)
@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a dry run names a secret header's secret but never its value"
)
def test_a_dry_run_shows_each_environments_request(
    daemon: BoundaryDaemon, api: FakeHttpApi, nothing_leaves: None
) -> None:
    _two_envs(daemon, api)
    args = {"q": "x", "cid": "SG"}
    test = _preview(daemon, "test", args).json()
    live = _preview(daemon, "live", args).json()

    assert test["environment"] == "test" and live["environment"] == "live"
    assert test["method"] == "POST"
    assert test["url"] == api.base_url + "/t/v1/eu-1/search?cid=SG"
    assert live["url"] == api.base_url + "/l/v1/us-1/search?cid=SG"
    assert test["body"] == '{"query": "x"}'
    assert (test["timeout_seconds"], test["timeout_source"]) == (30, "group")
    assert (live["timeout_seconds"], live["timeout_source"]) == (7, "environment")
    assert test["variables"] == {"region": "eu-1"}

    def headers(p: dict[str, Any]) -> dict[str, Any]:
        return {h["name"]: h for h in p["headers"]}

    t, li = headers(test), headers(live)
    assert t["X-Tenant"] == {"name": "X-Tenant", "value": "tenant-test", "secret": None}
    assert li["X-Tenant"]["value"] == "tenant-live"
    assert t["X-Client"]["value"] == "coffer-eu-1"
    assert t["Authorization"]["value"] == "Bearer ***"
    assert t["Authorization"]["secret"] == {
        "id": "secret/test-key",
        "name": "test-key",
        "scheme": "Bearer",
        "state": "present",
    }
    assert li["Authorization"]["secret"]["name"] == "live-key"
    text = str(test) + str(live)
    assert TEST_TOKEN not in text and LIVE_TOKEN not in text
    assert api.seen == []


def test_a_dry_run_reports_a_missing_secret_without_needing_it(
    daemon: BoundaryDaemon, api: FakeHttpApi, nothing_leaves: None
) -> None:
    _two_envs(daemon, api)
    get_secret_store().delete("secret/test-key")
    preview = _preview(daemon, "test", {"q": "x", "cid": "SG"}).json()
    auth = next(h for h in preview["headers"] if h["name"] == "Authorization")
    assert auth["secret"]["state"] == "missing" and auth["value"] == "Bearer ***"
    assert api.seen == []


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a dry run refuses what a call would refuse")
def test_a_dry_run_refuses_what_a_call_would(
    daemon: BoundaryDaemon, api: FakeHttpApi, nothing_leaves: None
) -> None:
    _two_envs(daemon, api)
    r = _preview(daemon, None, {"q": "x", "cid": "SG"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "CUSTOM_TOOL_ENVIRONMENT_REQUIRED")
    r = _preview(daemon, "test", {"q": "x"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "CUSTOM_TOOL_ARGUMENTS_INVALID")
    r = daemon.client.patch(f"{_GROUPS}/billing/environments/live", json={"enabled": False})
    assert r.status_code == 200, r.text
    r = _preview(daemon, "live", {"q": "x", "cid": "SG"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "CUSTOM_TOOL_ENVIRONMENT_DISABLED")
    draft = dict(_SEARCH, path="/v1/{env:nowhere}/search")
    r = daemon.client.post(
        f"{_GROUPS}/billing/preview",
        json={"tool": draft, "arguments": {"q": "x", "cid": "SG"}, "environment": "test"},
    )
    assert (r.status_code, r.json()["error"]["code"]) == (422, "CUSTOM_TOOL_REQUEST_INVALID")
    assert api.seen == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a test reports the request id but no cookie or credential"
)
def test_a_test_reports_allow_listed_response_headers(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _two_envs(daemon, api)
    api.echo_secret = TEST_TOKEN
    tool = {
        "name": "denied",
        "method": "GET",
        "path": "/forbidden",
        "input_schema": {"type": "object", "properties": {}},
    }
    r = daemon.client.post(
        f"{_GROUPS}/billing/test", json={"tool": tool, "arguments": {}, "environment": "test"}
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["status"] == 403
    seen = result["response_headers"]
    assert seen["x-request-id"] == "req-123"
    assert seen["x-trace-id"] == "trace-***"
    assert "server" in seen and "date" in seen
    for left_out in ("set-cookie", "www-authenticate", "x-internal-node"):
        assert left_out not in seen
    assert TEST_TOKEN not in r.text and "s3cr3t-cookie" not in r.text
