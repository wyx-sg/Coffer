"""Environments of a custom-tool group, and argument validation, against a real daemon.

Spec mcp-gateway "Keep a custom-tool group's environments in the group",
"Choose a custom tool's environment on every call", "Validate a custom tool's
arguments before any request" and "Wait for approval before a custom tool
sends its secret". Agents call through the real ``/mcp`` endpoint; the
upstream is a real socket that records every request it receives.
"""

from __future__ import annotations

import json
import pathlib
import time
from collections.abc import Iterator
from typing import Any

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.custom_tools import Agent, invocations, refusal, text_of
from tests.support.fake_http_api import FakeHttpApi, fake_http_api

CLAUDE = "a" * 32
TEST_TOKEN, LIVE_TOKEN = "tok-test-1111", "tok-live-2222"


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


def _env(
    name: str, url: str, *, secret: str | None = None, scheme: str = "Bearer", **extra: Any
) -> dict[str, Any]:
    headers = [{"name": "Authorization", "secret": secret, "scheme": scheme}] if secret else []
    return {"name": name, "base_url": url, "headers": headers, **extra}


def _group(d: BoundaryDaemon, envs: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
    r = d.client.post(
        "/api/v1/custom-tools", json={"name": "billing", "environments": envs, "tools": tools}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _approve_all(d: BoundaryDaemon, group: dict[str, Any]) -> dict[str, Any]:
    for approval_id in group["pending_approvals"]:
        d.approve(approval_id)
    return dict(d.client.get("/api/v1/custom-tools/billing").json())


_SEARCH = {
    "name": "search",
    "method": "POST",
    "path": "/v1/{env:region}/search",
    "changes_data": False,
    "input_schema": {
        "type": "object",
        "properties": {"q": {"type": "string"}, "cid": {"type": "string"}},
        "required": ["q"],
    },
}


def _two_envs(d: BoundaryDaemon, api: FakeHttpApi) -> dict[str, Any]:
    d.store("secret/test-key", TEST_TOKEN)
    d.store("secret/live-key", LIVE_TOKEN)
    group = _group(
        d,
        [
            _env("test", api.base_url + "/t", secret="test-key", variables={"region": "eu-1"}),
            _env("live", api.base_url + "/l", secret="live-key", variables={"region": "us-1"}),
        ],
        [_SEARCH],
    )
    return _approve_all(d, group)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="one group serves the same tools in several environments"
)
@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the advertised schema offers only enabled environments"
)
def test_one_group_serves_its_tools_in_several_environments(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _two_envs(daemon, api)
    r = daemon.client.post(
        "/api/v1/custom-tools/billing/environments",
        json=_env("uat", api.base_url + "/u", variables={"region": "eu-2"}, enabled=False),
    )
    assert r.status_code == 201, r.text
    listed = {n: t for n, t in Agent(daemon, CLAUDE).tools().items() if n.startswith("billing")}
    assert list(listed) == ["billing__search"]
    choice = listed["billing__search"]["inputSchema"]["properties"]["coffer_environment"]
    assert choice["enum"] == ["test", "live"]
    assert "coffer_environment" in listed["billing__search"]["inputSchema"]["required"]
    bad = dict(_SEARCH, name="bad")
    bad["input_schema"] = {
        "type": "object",
        "properties": {"coffer_environment": {"type": "string"}},
    }
    r = daemon.client.post("/api/v1/custom-tools/billing/tools", json=bad)
    assert r.status_code == 422 and "reserved" in r.text


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a variable is substituted per environment and refused in a base URL",
)
def test_a_variable_is_filled_per_environment(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    _two_envs(daemon, api)
    agent = Agent(daemon, CLAUDE)
    for env in ("test", "live"):
        agent.call("billing__search", {"q": "x", "coffer_environment": env})
    assert [s.path for s in api.seen] == ["/t/v1/eu-1/search", "/l/v1/us-1/search"]
    r = daemon.client.patch(
        "/api/v1/custom-tools/billing/environments/test",
        json={"base_url": api.base_url + "/{env:region}"},
    )
    assert r.status_code == 422
    r = daemon.client.patch(
        "/api/v1/custom-tools/billing/environments/live", json={"variables": {}}
    )
    assert r.status_code == 422 and "region" in r.text


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="concurrent calls in two environments do not mix"
)
def test_calls_in_two_environments_do_not_mix(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    _two_envs(daemon, api)
    agent = Agent(daemon, CLAUDE)
    for i in range(20):
        env = "test" if i % 2 == 0 else "live"
        agent.call("billing__search", {"q": f"q{i}", "cid": f"c{i}", "coffer_environment": env})
    assert len(api.seen) == 20
    for seen in api.seen:
        body = json.loads(seen.body)
        assert "coffer_environment" not in body and "coffer_environment" not in seen.path
        if seen.path.startswith("/t/"):
            assert seen.headers["authorization"] == f"Bearer {TEST_TOKEN}"
            assert "/eu-1/" in seen.path
        else:
            assert seen.path.startswith("/l/")
            assert seen.headers["authorization"] == f"Bearer {LIVE_TOKEN}"
            assert "/us-1/" in seen.path
        assert set(body) == {"q", "cid"}


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="an environment that is not registered or is off is refused before any request",
)
def test_an_unknown_off_or_missing_environment_is_refused(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(
        daemon,
        [
            _env("test", api.base_url),
            _env("live", api.base_url, enabled=False),
            _env("uat", api.base_url),
        ],
        [{"name": "ping", "method": "GET", "path": "/ping"}],
    )
    agent = Agent(daemon, CLAUDE)
    assert "CUSTOM_TOOL_ENVIRONMENT_UNKNOWN" in refusal(
        agent.call("billing__ping", {"coffer_environment": "prod"})
    )
    assert "CUSTOM_TOOL_ENVIRONMENT_DISABLED" in refusal(
        agent.call("billing__ping", {"coffer_environment": "live"})
    )
    assert "CUSTOM_TOOL_ENVIRONMENT_REQUIRED" in refusal(agent.call("billing__ping"))
    assert api.seen == []


_PAY = {
    "name": "pay",
    "method": "POST",
    "path": "/pay",
    "input_schema": {
        "type": "object",
        "required": ["amount"],
        "additionalProperties": False,
        "properties": {
            "amount": {"type": "integer", "minimum": 1, "maximum": 100},
            "currency": {"enum": ["EUR", "USD"]},
            "tags": {
                "type": "array",
                "maxItems": 3,
                "uniqueItems": True,
                "items": {"type": "string"},
            },
            "card": {"type": "string"},
            "iban": {"type": "string"},
        },
        "oneOf": [{"required": ["card"]}, {"required": ["iban"]}],
    },
}
_BAD_ARGS = {
    "amount": 0,
    "currency": "GBP",
    "tags": ["a", "b", "c", "d"],
    "note": "x",
    "card": "1",
    "iban": "2",
}
_EXPECTED = {
    ("/amount", "minimum"),
    ("/currency", "enum"),
    ("/tags", "maxItems"),
    ("/note", "additionalProperties"),
    ("/", "oneOf"),
}


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="invalid arguments are refused field by field with no upstream request",
)
def test_invalid_arguments_are_refused_with_no_upstream_request(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(daemon, [_env("test", api.base_url)], [_PAY])
    said = refusal(Agent(daemon, CLAUDE).call("billing__pay", _BAD_ARGS))
    assert "CUSTOM_TOOL_ARGUMENTS_INVALID" in said
    for path, keyword in _EXPECTED:
        assert f"{path} ({keyword})" in said
    for route, body in (
        ("/api/v1/custom-tools/billing/tools/pay/test", {"arguments": _BAD_ARGS}),
        ("/api/v1/custom-tools/billing/test", {"tool": _PAY, "arguments": _BAD_ARGS}),
        (
            "/api/v1/custom-tools/test",
            {"base_url": api.base_url, "tool": _PAY, "arguments": _BAD_ARGS},
        ),
    ):
        r = daemon.client.post(route, json=body)
        assert r.status_code == 422, r.text
        error = r.json()["error"]
        assert error["code"] == "CUSTOM_TOOL_ARGUMENTS_INVALID"
        assert {(e["path"], e["keyword"]) for e in error["details"]["errors"]} == _EXPECTED
    assert api.seen == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a malformed argument schema is refused when saved"
)
def test_a_malformed_schema_is_refused_when_saved(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    _group(daemon, [_env("test", api.base_url)], [])
    for schema in (
        {"type": "object", "properties": {"n": {"type": "integer", "minimum": "1"}}},
        {"type": "object", "properties": {"s": {"type": "string", "pattern": "("}}},
        {"type": "object", "properties": {"x": {"$ref": "#/$defs/missing"}}},
    ):
        tool = {"name": "t", "method": "GET", "path": "/t", "input_schema": schema}
        r = daemon.client.post("/api/v1/custom-tools/billing/tools", json=tool)
        assert r.status_code == 422, r.text
        assert "JSON Schema" in r.text
    assert daemon.client.get("/api/v1/custom-tools/billing").json()["tools"] == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a missing or unapproved secret is refused before any request"
)
@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an approval in one environment does not open another"
)
def test_each_environment_waits_on_its_own_secret(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    daemon.store("secret/test-key", TEST_TOKEN)
    daemon.store("secret/live-key", LIVE_TOKEN)
    group = _group(
        daemon,
        [_env("test", api.base_url + "/t", secret="test-key"), _env("live", api.base_url + "/l")],
        [{"name": "ping", "method": "GET", "path": "/ping"}],
    )
    [test_approval] = group["pending_approvals"]
    daemon.approve(test_approval)
    # ``live`` now binds a secret too, and waits on its own approval.
    r = daemon.client.patch(
        "/api/v1/custom-tools/billing/environments/live",
        json={"headers": [{"name": "Authorization", "secret": "live-key", "scheme": "Bearer"}]},
    )
    assert r.status_code == 200, r.text
    envs = {e["name"]: e for e in r.json()["environments"]}
    assert envs["test"]["secret_state"] == "present"
    [live_approval] = envs["live"]["pending_approvals"]
    agent = Agent(daemon, CLAUDE)
    agent.call("billing__ping", {"coffer_environment": "test"})
    assert api.seen[-1].headers["authorization"] == f"Bearer {TEST_TOKEN}"
    said = refusal(agent.call("billing__ping", {"coffer_environment": "live"}))
    assert "SECRET_BINDING_PENDING" in said and f"coffer approval approve {live_approval}" in said
    assert len(api.seen) == 1
    # Moving ``test`` asks again for ``test`` only.
    r = daemon.client.patch(
        "/api/v1/custom-tools/billing/environments/test", json={"base_url": api.base_url + "/t2"}
    )
    envs = {e["name"]: e for e in r.json()["environments"]}
    assert envs["test"]["secret_state"] == "pending_approval"
    assert envs["live"]["pending_approvals"] == [live_approval]
    # A secret whose value is gone from this machine stops only its environment.
    for approval_id in envs["test"]["pending_approvals"] + [live_approval]:
        daemon.approve(approval_id)
    # The ciphertext is gone from this machine (another machine's sync, say),
    # its approval untouched.
    for enc in daemon.home.rglob("test-key.enc"):
        enc.unlink()
    assert "SECRET_MISSING" in refusal(agent.call("billing__ping", {"coffer_environment": "test"}))
    agent.call("billing__ping", {"coffer_environment": "live"})
    assert len(api.seen) == 2
    assert api.seen[-1].headers["authorization"] == f"Bearer {LIVE_TOKEN}"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a group from before environments reads as one environment"
)
def test_a_group_from_before_environments_reads_as_default(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    daemon.store("secret/old-key", TEST_TOKEN)
    r = daemon.client.post(
        "/api/v1/resources",
        json={
            "kind": "mcp_server",
            "name": "legacy",
            "config": {
                "transport": {
                    "type": "http_api",
                    "base_url": api.base_url,
                    "secret_refs": {"Authorization": "secret/old-key"},
                    "auth_schemes": {"Authorization": "Bearer"},
                    "tools": [{"name": "ping", "method": "GET", "path": "/ping"}],
                }
            },
        },
    )
    assert r.status_code == 201, r.text
    group = daemon.client.get("/api/v1/custom-tools/legacy").json()
    [env] = group["environments"]
    assert env["name"] == "default" and env["base_url"].rstrip("/") == api.base_url
    for approval_id in group["pending_approvals"]:
        daemon.approve(approval_id)
    [pending] = daemon.pending(destination_uid=group["uid"]) or [None]
    Agent(daemon, CLAUDE).call("legacy__ping")
    assert api.seen[-1].headers["authorization"] == f"Bearer {TEST_TOKEN}"
    # The lifted environment keeps the bare header as its slot.
    assert daemon.boundary.bindings("secret/old-key")[0].slot == "Authorization"
    assert pending is None or pending["status"] != "pending"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an environment is added, renamed, switched off and deleted"
)
def test_an_environment_is_added_renamed_switched_and_deleted(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(daemon, [_env("default", api.base_url)], [])
    base = "/api/v1/custom-tools/billing/environments"
    assert daemon.client.post(base, json=_env("staging", api.base_url)).status_code == 201
    assert daemon.client.patch(f"{base}/staging", json={"name": "uat"}).status_code == 200
    r = daemon.client.patch(f"{base}/uat", json={"enabled": False})
    assert [e["enabled"] for e in r.json()["environments"]] == [True, False]
    assert daemon.client.delete(f"{base}/uat").status_code == 200
    r = daemon.client.delete(f"{base}/default")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CUSTOM_TOOL_LAST_ENVIRONMENT"
    events = [e["event_type"] for e in daemon.audit_all()]
    assert events.count("resource_updated") >= 4


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a saved tool is tested in a chosen environment and reports its target",
)
def test_a_saved_tool_is_tested_in_its_environment(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(
        daemon,
        [_env("test", api.base_url + "/t"), _env("live", api.base_url + "/l")],
        [{"name": "status", "method": "GET", "path": "/status"}],
    )
    r = daemon.client.post(
        "/api/v1/custom-tools/billing/tools/status/test", json={"environment": "live"}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["environment"] == "live" and out["url"] == f"{api.base_url}/l/status"
    assert [s.path for s in api.seen] == ["/l/status"]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a custom tool's call names its environment in the log"
)
def test_the_invocation_log_names_the_environment(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    group = _group(
        daemon,
        [_env("test", api.base_url + "/t"), _env("live", api.base_url + "/l")],
        [{"name": "ping", "method": "GET", "path": "/ping"}],
    )
    agent = Agent(daemon, CLAUDE)
    text_of(agent.call("billing__ping", {"coffer_environment": "live"}))
    rows = invocations(daemon, group["uid"], expect=1)
    assert rows[0]["environment"] == "live"
    assert "authorization" not in json.dumps(rows).lower()


@pytest.mark.acceptance(spec="mcp-gateway", scenario="re-import keeps the group's environments")
def test_reimport_keeps_every_environment(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Billing", "version": "1"},
        "servers": [{"url": "https://elsewhere.example"}],
        "paths": {"/ping": {"get": {"operationId": "ping"}}},
    }
    daemon.store("secret/test-key", TEST_TOKEN)
    r = daemon.client.post(
        "/api/v1/custom-tools",
        json={
            "name": "billing",
            "environments": [
                _env("test", api.base_url + "/t", secret="test-key", variables={"region": "eu"}),
                _env("live", api.base_url + "/l"),
            ],
            "tools": [{"name": "ping", "method": "GET", "path": "/ping", "operation": "GET /ping"}],
            "source": {"kind": "file", "location": "openapi.json"},
        },
    )
    assert r.status_code == 201, r.text
    before = _approve_all(daemon, r.json())["environments"]
    r = daemon.client.post(
        "/api/v1/custom-tools/billing/reimport", json={"document": json.dumps(spec), "add": []}
    )
    assert r.status_code == 200, r.text
    after = r.json()["environments"]
    assert after == before
    assert r.json()["pending_approvals"] == []


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="invalid arguments are refused field by field with no upstream request",
)
def test_a_wrong_argument_type_through_the_gateway_is_refused_in_band(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(daemon, [_env("test", api.base_url)], [_PAY])
    agent = Agent(daemon, CLAUDE)
    for bad in ({"amount": "ten", "card": "1"}, {"amount": 5.5, "card": "1"}, {"amount": [5]}):
        answer = agent.call("billing__pay", bad)
        assert "error" not in answer and answer["result"]["isError"] is True, answer
        assert "CUSTOM_TOOL_ARGUMENTS_INVALID" in text_of(answer)
        assert "/amount (type)" in text_of(answer)
    assert api.seen == []


_HEADER_TOOL = {
    "name": "header",
    "method": "GET",
    "path": "/h",
    "headers": {"X-Arg": "{value}"},
    "input_schema": {"type": "object", "properties": {"value": {"type": "string"}}},
}


def test_a_header_value_with_a_line_break_is_refused_before_any_request(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(daemon, [_env("test", api.base_url)], [_HEADER_TOOL])
    agent = Agent(daemon, CLAUDE)
    for bad in ("x\r\nX-Fake: y", "x\nX-Fake: y", "x\rX-Fake: y"):
        answer = agent.call("billing__header", {"value": bad, "coffer_environment": "test"})
        assert refusal(answer)
    assert api.seen == []
    # The same tool with a clean value does reach the API, carrying the header.
    agent.call("billing__header", {"value": "clean", "coffer_environment": "test"})
    assert [s.headers.get("x-arg") for s in api.seen] == ["clean"]


def test_a_header_line_break_is_refused_before_the_secret_is_sent(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    daemon.store("secret/test-key", TEST_TOKEN)
    group = _group(daemon, [_env("test", api.base_url, secret="test-key")], [_HEADER_TOOL])
    _approve_all(daemon, group)
    agent = Agent(daemon, CLAUDE)
    answer = agent.call(
        "billing__header", {"value": "x\r\nX-Fake: y", "coffer_environment": "test"}
    )
    refusal(answer)
    assert api.seen == []
    assert TEST_TOKEN not in json.dumps(answer)


def test_a_call_past_its_environments_timeout_is_an_error(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    _group(
        daemon,
        [_env("uat", api.base_url, timeout_seconds=1)],
        [{"name": "slow", "method": "GET", "path": "/slow"}],
    )
    started = time.monotonic()
    answer = Agent(daemon, CLAUDE).call("billing__slow", {"coffer_environment": "uat"})
    elapsed = time.monotonic() - started
    assert refusal(answer)
    assert elapsed < 2.9, elapsed


def test_one_group_sends_each_environments_secret_behind_its_own_scheme(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    daemon.store("secret/bearer-key", TEST_TOKEN)
    daemon.store("secret/token-key", LIVE_TOKEN)
    group = _group(
        daemon,
        [
            _env("test", api.base_url + "/t", secret="bearer-key", scheme="Bearer"),
            _env("uat", api.base_url + "/u", secret="token-key", scheme="Token"),
        ],
        [{"name": "ping", "method": "GET", "path": "/ping"}],
    )
    _approve_all(daemon, group)
    agent = Agent(daemon, CLAUDE)
    for env in ("test", "uat"):
        assert text_of(agent.call("billing__ping", {"coffer_environment": env})).startswith(
            "HTTP 200"
        )
    assert [s.headers["authorization"] for s in api.seen] == [
        f"Bearer {TEST_TOKEN}",
        f"Token {LIVE_TOKEN}",
    ]


def test_a_basic_scheme_secret_header_is_refused_when_saved(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    daemon.store("secret/basic-key", TEST_TOKEN)
    r = daemon.client.post(
        "/api/v1/custom-tools",
        json={
            "name": "billing",
            "base_url": api.base_url,
            "headers": [{"name": "Authorization", "secret": "basic-key", "scheme": "Basic"}],
            "tools": [{"name": "echo", "method": "GET", "path": "/echo"}],
        },
    )
    assert r.status_code == 422, r.text
    assert TEST_TOKEN not in r.text
    assert daemon.client.get("/api/v1/custom-tools/billing").status_code == 404
