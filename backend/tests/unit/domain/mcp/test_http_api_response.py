"""Response rules (spec mcp-gateway "Judge a custom tool's answer by its group's
response rules"): reading values, comparing them, and refusing malformed rules."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_response import HttpApiResponse, ResponseRule, judge


def rule(**kw: Any) -> ResponseRule:
    return ResponseRule.model_validate(kw)


def json_rule(pointer: str, *ok: str, missing: str = "ok") -> ResponseRule:
    return rule(source="json", name=pointer, ok_values=list(ok), missing=missing)


def test_no_rules_never_fail() -> None:
    assert judge([], status=200, headers={}, body="") is None


@pytest.mark.parametrize(
    ("body", "ok", "fails"),
    [
        ('{"code": 0}', "0", False),
        ('{"code": 0.0}', "0", False),
        ('{"code": "0"}', "0", False),
        ('{"code": 1}', "0", True),
        ('{"code": true}', "true", False),
        ('{"code": null}', "null", False),
        ('{"code": {"a": 1}}', '{"a":1}', False),
    ],
)
def test_json_values_compare_as_text(body: str, ok: str, fails: bool) -> None:
    failure = judge([json_rule("/code", ok)], status=200, headers={}, body=body)
    assert (failure is not None) is fails


def test_pointer_walks_arrays_and_escapes() -> None:
    body = '{"errors": [{"a/b": {"~c": "E1"}}]}'
    failure = judge([json_rule("/errors/0/a~1b/~0c", "OK")], status=200, headers={}, body=body)
    assert failure is not None and failure.value == "E1"


@pytest.mark.parametrize("body", ["", "not json", '{"other": 1}', "[1]"])
def test_a_missing_field_follows_the_rule(body: str) -> None:
    assert judge([json_rule("/code", "0")], status=200, headers={}, body=body) is None
    failure = judge([json_rule("/code", "0", missing="error")], status=200, headers={}, body=body)
    assert failure is not None and failure.value is None
    assert "is missing" in failure.describe()


def test_a_truncated_body_is_not_parsed() -> None:
    failure = judge(
        [json_rule("/code", "0", missing="error")],
        status=200,
        headers={},
        body='{"code": 0}',
        truncated=True,
    )
    assert failure is not None and failure.value is None


def test_header_names_are_case_insensitive_and_the_message_is_cut() -> None:
    r = rule(
        source="header",
        name="X-Result",
        ok_values=["OK"],
        message={"source": "json", "name": "/msg"},
    )
    assert r.name == "x-result"
    failure = judge(
        [r], status=200, headers={"X-RESULT": "NO"}, body='{"msg": "' + "m" * 999 + '"}'
    )
    assert failure is not None and failure.value == "NO"
    assert failure.message is not None and len(failure.message) == 256


def test_every_rule_must_hold_and_the_first_broken_one_is_reported() -> None:
    rules = [rule(source="status", ok_values=["200"]), json_rule("/code", "0")]
    assert judge(rules, status=200, headers={}, body='{"code": 0}') is None
    first = judge(rules, status=201, headers={}, body='{"code": 9}')
    assert first is not None and first.rule.source == "status" and first.value == "201"


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "header", "name": "Set-Cookie", "ok_values": ["x"]},
        {"source": "header", "name": "authorization", "ok_values": ["x"]},
        {"source": "header", "name": "bad header", "ok_values": ["x"]},
        {"source": "header", "name": "", "ok_values": ["x"]},
        {"source": "json", "name": "code", "ok_values": ["0"]},
        {"source": "status", "name": "x", "ok_values": ["200"]},
        {"source": "status", "ok_values": ["OK"]},
        {"source": "status", "ok_values": ["700"]},
        {"source": "json", "name": "/c", "ok_values": []},
        {"source": "json", "name": "/c", "ok_values": ["x" * 201]},
        {
            "source": "json",
            "name": "/c",
            "ok_values": ["0"],
            "message": {"source": "status", "name": ""},
        },
        {
            "source": "json",
            "name": "/c",
            "ok_values": ["0"],
            "message": {"source": "header", "name": "Cookie"},
        },
    ],
)
def test_a_malformed_rule_is_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ResponseRule.model_validate(bad)


def test_diagnostic_headers_are_lowered_deduplicated_and_never_sensitive() -> None:
    settings = HttpApiResponse(diagnostic_headers=["X-Req", "x-req", "X-Other"])
    assert settings.diagnostic_headers == ["x-req", "x-other"]
    with pytest.raises(ValidationError):
        HttpApiResponse(diagnostic_headers=["WWW-Authenticate"])
    with pytest.raises(ValidationError):
        HttpApiResponse(rules=[json_rule("/c", "0")] * 11)


def test_a_tool_follows_its_group_unless_it_sets_its_own() -> None:
    group_rule = json_rule("/code", "0")
    transport = HttpApiTransport.model_validate(
        {
            "environments": [{"name": "default", "base_url": "https://api.example"}],
            "response": {"rules": [group_rule.model_dump()]},
            "tools": [
                {"name": "follows", "path": "/a"},
                {"name": "status_only", "path": "/b", "response_rules": []},
            ],
        }
    )
    follows, status_only = transport.tools
    assert transport.rules_for(follows) == [group_rule]
    assert transport.rules_for(status_only) == []
    # A group stored before response settings existed reads with none.
    assert HttpApiTool(name="t", path="/t").response_rules is None
