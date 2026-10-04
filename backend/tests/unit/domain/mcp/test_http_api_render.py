"""Rendering a custom tool's request (design add-http-custom-tools §3)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_render import RenderError, render_request

_SCHEMA = {
    "type": "object",
    "properties": {"id": {}, "status": {}, "tags": {}, "n": {}, "note": {}},
    "required": ["id"],
}


def _render(path: str, args: dict, **kw):  # type: ignore[no-untyped-def]
    return render_request(
        base_url=kw.pop("base_url", "https://api.example/v2/"),
        method=kw.pop("method", "GET"),
        path=path,
        group_headers=kw.pop("group_headers", {}),
        tool_headers=kw.pop("tool_headers", {}),
        body_template=kw.pop("body_template", None),
        input_schema=kw.pop("input_schema", _SCHEMA),
        arguments=args,
    )


def test_a_path_value_cannot_change_the_path_or_the_host():
    r = _render("/invoices/{id}", {"id": "../x/?q=1#@evil.example"})
    assert r.url == "https://api.example/v2/invoices/..%2Fx%2F%3Fq%3D1%23%40evil.example"


def test_an_absent_query_argument_drops_its_pair_and_a_list_repeats():
    r = _render(
        "/invoices/{id}?status={status}&tag={tags}&limit=10", {"id": "1", "tags": ["a", "b c"]}
    )
    assert r.url == "https://api.example/v2/invoices/1?tag=a&tag=b%20c&limit=10"


def test_a_missing_required_argument_is_named():
    with pytest.raises(RenderError, match="id"):
        _render("/invoices/{id}", {})


def test_a_body_template_fills_json_values_and_escapes_inside_strings():
    r = _render(
        "/x/{id}",
        {"id": "1", "n": 3, "note": 'say "hi"'},
        method="POST",
        body_template='{"n": {n}, "msg": "note: {note}", "status": {status}}',
    )
    assert json.loads(r.body or b"") == {"n": 3, "msg": 'note: say "hi"', "status": None}
    assert r.headers["Content-Type"] == "application/json"


def test_a_body_template_that_is_not_json_is_an_error():
    with pytest.raises(RenderError, match="valid JSON"):
        _render("/x/{id}", {"id": "1"}, method="POST", body_template="{n} and {")


def test_without_a_template_unused_arguments_are_the_body_of_a_post_only():
    post = _render("/x/{id}", {"id": "1", "n": 2}, method="POST")
    assert json.loads(post.body or b"") == {"n": 2}
    get = _render("/x/{id}", {"id": "1", "n": 2})
    assert get.body is None


def test_a_tool_header_hole_is_rendered_and_dropped_when_absent():
    r = _render("/x/{id}", {"id": "1"}, tool_headers={"X-Id": "{id}", "X-Note": "{note}"})
    assert r.headers == {"X-Id": "1"}


def test_a_hole_the_schema_does_not_declare_is_refused():
    with pytest.raises(ValidationError, match="'id'"):
        HttpApiTool(name="get", path="/items/{id}")


@pytest.mark.parametrize("path", ["//evil.example/x", "https://evil.example/", "items", "/a b"])
def test_a_path_that_is_not_a_path_is_refused(path: str):
    with pytest.raises(ValidationError):
        HttpApiTool(name="get", path=path)


def test_the_changes_data_flag_defaults_by_method():
    assert HttpApiTool(name="a", path="/a").effective_changes_data is False
    assert HttpApiTool(name="b", method="DELETE", path="/b").effective_changes_data is True
    assert (
        HttpApiTool(name="c", method="POST", path="/c", changes_data=False).effective_changes_data
        is False
    )


def test_a_static_group_header_that_looks_like_a_secret_is_refused():
    with pytest.raises(ValidationError, match="looks like a secret"):
        HttpApiTransport(base_url="https://api.example", headers={"Authorization": "Bearer abc"})


def test_a_header_appears_once_in_a_group_whether_plain_or_secret():
    with pytest.raises(ValidationError, match="once"):
        HttpApiTransport(
            base_url="https://api.example",
            headers={"authorization": "x"},
            secret_refs={"Authorization": "secret/x"},
        )


def test_a_secret_header_must_be_a_valid_header_name():
    with pytest.raises(ValidationError, match="not a valid header name"):
        HttpApiTransport(base_url="https://api.example", secret_refs={"bad name": "secret/x"})


def test_tool_names_are_unique_in_a_group():
    t = {"name": "a", "path": "/a"}
    with pytest.raises(ValidationError, match="unique"):
        HttpApiTransport(base_url="https://api.example", tools=[t, t])
