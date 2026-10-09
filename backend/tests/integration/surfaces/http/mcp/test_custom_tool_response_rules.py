"""A custom tool's answer judged by its group's response rules (spec mcp-gateway
"Judge a custom tool's answer by its group's response rules" and "Report what a
custom tool's test reached").

A real daemon, a fake HTTP API scripted per path, and agents speaking JSON-RPC
to ``/mcp``. Every API convention here is invented for the test — the last
scenario shapes one like an RPC gateway's error headers to show such a
convention is only a rule the group declares.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.custom_tools import (
    SECRET_VALUE,
    Agent,
    create_group,
    get_group,
    invocations,
    text_of,
    tool,
)
from tests.support.fake_http_api import Answer, FakeHttpApi, fake_http_api

CLAUDE = "a" * 32
GROUPS = "/api/v1/custom-tools"
JSON = {"Content-Type": "application/json"}

RESULT_CODE_RULE: dict[str, Any] = {
    "source": "header",
    "name": "X-Result-Code",
    "ok_values": ["OK"],
    "message": {"source": "header", "name": "X-Result-Text"},
}


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


def set_response(d: BoundaryDaemon, group: str, response: dict[str, Any]) -> dict[str, Any]:
    r = d.client.patch(f"{GROUPS}/{group}", json={"response": response})
    assert r.status_code == 200, r.text
    return dict(r.json())


def statuses(d: BoundaryDaemon, uid: str, expect: int) -> list[tuple[str, str]]:
    rows = invocations(d, uid, expect=expect)
    return sorted((r["capability_key"], r["status"]) for r in rows)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an answer with no response rules is judged by its status"
)
def test_an_answer_with_no_rules_is_judged_by_its_status(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    api.answers["/empty"] = Answer(200, JSON, b"")
    api.answers["/coded"] = Answer(200, JSON, b'{"code": 7}')
    api.answers["/nothing"] = Answer(204, {}, b"")
    group = create_group(
        daemon,
        "plain",
        api.base_url,
        [
            tool("empty", "GET", "/empty"),
            tool("coded", "GET", "/coded"),
            tool("none", "GET", "/nothing"),
        ],
    )
    agent = Agent(daemon, CLAUDE)
    empty, coded, none = (agent.call(f"plain__{n}") for n in ("empty", "coded", "none"))
    for result in (empty, coded, none):
        assert result["result"].get("isError") in (None, False)
    assert text_of(empty) == "HTTP 200 OK\n\n(empty body)"
    assert text_of(coded) == 'HTTP 200 OK\n\n{"code": 7}'
    assert text_of(none).startswith("HTTP 204 No Content")
    assert statuses(daemon, group["uid"], 3) == [("coded", "ok"), ("empty", "ok"), ("none", "ok")]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a header rule turns a 200 into an error with the API's message"
)
def test_a_header_rule_turns_a_200_into_an_error(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    api.answers["/deny"] = Answer(
        200, {"X-Result-Code": "DENIED", "X-Result-Text": "quota exhausted"}, b""
    )
    api.answers["/allow"] = Answer(200, {"X-Result-Code": "OK", **JSON}, b'{"items": [1]}')
    group = create_group(
        daemon, "acme", api.base_url, [tool("deny", "GET", "/deny"), tool("allow", "GET", "/allow")]
    )
    set_response(daemon, "acme", {"rules": [RESULT_CODE_RULE]})
    agent = Agent(daemon, CLAUDE)
    denied = agent.call("acme__deny")
    assert denied["result"]["isError"] is True
    text = text_of(denied)
    assert text.startswith("HTTP 200 OK\n")
    assert "x-result-code: DENIED" in text and "x-result-text: quota exhausted" in text
    assert (
        'Response rule failed: header x-result-code = "DENIED" (success: "OK"): quota exhausted'
        in text
    )
    assert text.endswith("(empty body)")
    allowed = agent.call("acme__allow")
    assert allowed["result"].get("isError") in (None, False)
    assert text_of(allowed).endswith('{"items": [1]}')
    assert statuses(daemon, group["uid"], 2) == [("allow", "ok"), ("deny", "error")]


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a JSON field rule judges the body and a missing field follows the rule",
)
def test_a_json_rule_judges_the_body(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    rule = {
        "source": "json",
        "name": "/status/code",
        "ok_values": ["0"],
        "missing": "error",
        "message": {"source": "json", "name": "/status/message"},
    }
    api.answers["/a"] = Answer(200, JSON, b'{"status": {"code": 0}}')
    api.answers["/b"] = Answer(200, JSON, b'{"status": {"code": 3, "message": "not found"}}')
    api.answers["/c"] = Answer(200, {"Content-Type": "text/html"}, b"<html>oops</html>")
    create_group(
        daemon,
        "acme",
        api.base_url,
        [tool(n, "GET", f"/{n}", response_rules=[rule]) for n in ("a", "b", "c")],
    )
    agent = Agent(daemon, CLAUDE)
    assert agent.call("acme__a")["result"].get("isError") in (None, False)
    found = agent.call("acme__b")
    assert found["result"]["isError"] is True
    assert 'json /status/code = "3" (success: "0"): not found' in text_of(found)
    broken = agent.call("acme__c")
    assert broken["result"]["isError"] is True
    assert "json /status/code is missing" in text_of(broken)
    assert "<html>oops</html>" in text_of(broken)


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a tool's own rules replace its group's")
def test_a_tools_own_rules_replace_its_groups(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    create_group(
        daemon,
        "acme",
        api.base_url,
        [tool("follows", "GET", "/x"), tool("own", "GET", "/y", response_rules=[])],
    )
    shown = set_response(daemon, "acme", {"rules": [{**RESULT_CODE_RULE, "missing": "error"}]})
    by_name = {t["name"]: t for t in shown["tools"]}
    assert by_name["follows"]["response_rules"] is None
    assert by_name["own"]["response_rules"] == []
    assert shown["response"]["rules"][0]["name"] == "x-result-code"
    agent = Agent(daemon, CLAUDE)
    assert agent.call("acme__follows")["result"]["isError"] is True
    assert agent.call("acme__own")["result"].get("isError") in (None, False)


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a malformed response rule is refused")
def test_a_malformed_response_rule_is_refused(daemon: BoundaryDaemon, api: FakeHttpApi) -> None:
    create_group(daemon, "acme", api.base_url, [tool("x", "GET", "/x")])
    before = get_group(daemon, "acme")
    bad_rules: list[dict[str, Any]] = [
        {"source": "header", "name": "Authorization", "ok_values": ["x"]},
        {"source": "json", "name": "code", "ok_values": ["0"]},
        {"source": "status", "ok_values": ["OK"]},
        {"source": "header", "name": "X-Result-Code", "ok_values": []},
    ]
    for rule in bad_rules:
        r = daemon.client.patch(f"{GROUPS}/acme", json={"response": {"rules": [rule]}})
        assert r.status_code in (400, 422), (rule, r.text)
        r = daemon.client.patch(f"{GROUPS}/acme/tools/x", json={"response_rules": [rule]})
        assert r.status_code in (400, 422), (rule, r.text)
    after = get_group(daemon, "acme")
    assert after["response"] == before["response"]
    assert after["tools"] == before["tools"]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a test, the command line and the agent judge an answer alike"
)
def test_a_test_and_the_agent_judge_an_answer_alike(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    api.answers["/deny"] = Answer(200, {"X-Result-Code": "DENIED"}, b"")
    group = create_group(daemon, "acme", api.base_url, [tool("deny", "GET", "/deny")])
    set_response(daemon, "acme", {"rules": [RESULT_CODE_RULE]})
    r = daemon.client.post(f"{GROUPS}/acme/tools/deny/test", json={"arguments": {}})
    assert r.status_code == 200, r.text
    tested = r.json()
    assert tested["ok"] is False and tested["status"] == 200 and tested["body_bytes"] == 0
    assert tested["response_headers"]["x-result-code"] == "DENIED"
    failure = tested["rule_failure"]
    assert failure["value"] == "DENIED" and failure["message"] is None
    assert failure["rule"]["name"] == "x-result-code"
    assert failure["summary"] == 'header x-result-code = "DENIED" (success: "OK")'
    called = Agent(daemon, CLAUDE).call("acme__deny")
    assert called["result"]["isError"] is True
    assert failure["summary"] in text_of(called)
    # A test is not an agent's call: only the call is recorded.
    assert statuses(daemon, group["uid"], 1) == [("deny", "error")]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an API's error header convention is a rule the group declares"
)
def test_an_error_header_convention_is_a_declared_rule(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    # The answers a real RPC gateway gave: an auth error, then a success.
    api.answers["/rpc/auth-error"] = Answer(
        200,
        {
            "Server": "SGW",
            "Content-Type": "application/json",
            "X-Sp-Error": "101",
            "X-Sp-Errmsg": "ERROR_SP_NEED_AUTH",
        },
        b"",
    )
    api.answers["/rpc/ok"] = Answer(
        200,
        {"Content-Type": "application/json", "X-Sp-Error": "0", "X-Sp-Errmsg": "SUCCESS"},
        b'{"user_list": [{"userid": 1}], "query_flag": 111}',
    )
    create_group(
        daemon,
        "rpc",
        api.base_url,
        [tool("denied", "POST", "/rpc/auth-error"), tool("ok", "POST", "/rpc/ok")],
    )
    agent = Agent(daemon, CLAUDE)
    # With no rules, both are successes: nothing about this convention is built in.
    assert agent.call("rpc__denied")["result"].get("isError") in (None, False)
    assert agent.call("rpc__ok")["result"].get("isError") in (None, False)
    set_response(
        daemon,
        "rpc",
        {
            "diagnostic_headers": ["x-sp-requestid"],
            "rules": [
                {
                    "source": "header",
                    "name": "x-sp-error",
                    "ok_values": ["0"],
                    "missing": "ok",
                    "message": {"source": "header", "name": "x-sp-errmsg"},
                }
            ],
        },
    )
    denied = agent.call("rpc__denied")
    assert denied["result"]["isError"] is True
    text = text_of(denied)
    # A failed call names every diagnostic header (the fake server adds its own name).
    assert "x-sp-error: 101" in text and "SGW" in text
    assert '"101" (success: "0"): ERROR_SP_NEED_AUTH' in text
    ok = agent.call("rpc__ok")
    assert ok["result"].get("isError") in (None, False)
    assert text_of(ok).endswith('{"user_list": [{"userid": 1}], "query_flag": 111}')
    assert "x-sp-error: 0" in text_of(ok) and "server" not in text_of(ok)


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a group's named headers reach the agent and a credential header cannot be named",
)
def test_named_headers_reach_the_agent_and_a_credential_cannot_be_named(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    api.echo_secret = SECRET_VALUE
    api.answers["/x"] = Answer(
        200,
        {
            "X-Backend-Region": "eu-" + SECRET_VALUE,
            "Server": "edge",
            "Set-Cookie": "session=abc",
            **JSON,
        },
        b'{"ok": true}',
    )
    create_group(daemon, "acme", api.base_url, [tool("x", "GET", "/x")])
    set_response(daemon, "acme", {"diagnostic_headers": ["X-Backend-Region"]})
    text = text_of(Agent(daemon, CLAUDE).call("acme__x"))
    assert "x-backend-region: eu-***" in text
    assert "server" not in text and "session=abc" not in text and SECRET_VALUE not in text
    tested = daemon.client.post(f"{GROUPS}/acme/tools/x/test", json={"arguments": {}}).json()
    assert tested["response_headers"]["x-backend-region"] == "eu-***"
    assert tested["response_headers"]["server"].endswith("edge")
    assert "set-cookie" not in tested["response_headers"]
    assert tested["body_bytes"] == len(b'{"ok": true}')
    before = get_group(daemon, "acme")["response"]
    r = daemon.client.patch(
        f"{GROUPS}/acme", json={"response": {"diagnostic_headers": ["Set-Cookie"]}}
    )
    assert r.status_code in (400, 422), r.text
    assert get_group(daemon, "acme")["response"] == before
    assert json.dumps(before) == json.dumps(
        {"diagnostic_headers": ["x-backend-region"], "rules": []}
    )
