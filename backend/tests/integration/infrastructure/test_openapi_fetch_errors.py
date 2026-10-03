"""Where an unreadable spec broke, what an operation's text is, and why a URL
did not answer (spec mcp-gateway "Import custom tools from an OpenAPI document")."""

from __future__ import annotations

import asyncio
import json
import socket

import httpx
import pytest

from coffer.domain.mcp.custom_tool_errors import OpenApiUnreachable, OpenApiUnreadable
from coffer.infrastructure.mcp import openapi_fetch
from coffer.infrastructure.mcp.openapi_fetch import locate_operations, parse_document

_YAML = """\
openapi: 3.0.0
paths:
  /invoices:
    get:
      operationId: listInvoices
    post:
      operationId: createInvoice
      requestBody:
        required: true
  /charges/{id}:
    delete:
      operationId: voidCharge
"""


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an unreadable spec says where it broke")
def test_a_json_syntax_error_names_its_line_and_column():
    text = '{\n  "openapi": "3.0.0",\n  "paths": {\n    "a": 1\n    "b": 2\n  }\n}'
    with pytest.raises(OpenApiUnreadable) as caught:
        parse_document(text)
    assert caught.value.error_details == {"line": 5, "column": 5}


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an unreadable spec says where it broke")
def test_a_yaml_syntax_error_names_its_line_and_column():
    with pytest.raises(OpenApiUnreadable) as caught:
        parse_document("openapi: 3.0.0\npaths:\n  /a:\n   get: [unclosed\n")
    assert caught.value.error_details["line"] >= 4
    assert "column" in caught.value.error_details


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="the import preview shows each operation's source"
)
def test_each_operation_is_located_by_its_lines():
    found = locate_operations(_YAML)
    post = found["POST /invoices"]
    assert (post.start_line, post.end_line) == (6, 9)
    assert post.text.splitlines()[0] == "    post:"
    assert found["GET /invoices"].end_line == 5
    last = found["DELETE /charges/{id}"]
    assert last.text.splitlines()[-1].strip() == "operationId: voidCharge"


def test_a_json_document_is_located_too():
    doc = json.dumps({"openapi": "3.0.0", "paths": {"/a": {"get": {"x": 1}}}}, indent=2)
    found = locate_operations(doc)
    assert found["GET /a"].start_line == 5


def test_a_document_that_cannot_be_composed_locates_nothing():
    assert locate_operations("paths: [unclosed") == {}


class _Raising:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __call__(self, *a, **k):
        raise self._exc


def _fetch_with(monkeypatch: pytest.MonkeyPatch, exc: Exception):
    async def passes(url: str) -> None:
        return None

    monkeypatch.setattr(openapi_fetch, "_guard", passes)

    class Client:
        def __init__(self, *a, **k) -> None: ...
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        def stream(self, *a, **k):
            raise exc

    monkeypatch.setattr(openapi_fetch.httpx, "AsyncClient", Client)
    return asyncio.run(openapi_fetch.fetch_document("https://spec.example/openapi.json"))


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an unreachable spec URL says why")
@pytest.mark.parametrize(
    ("exc", "reason"),
    [
        (httpx.ReadTimeout("slow"), "timeout"),
        (_chain := httpx.ConnectError("x"), "unreachable"),
    ],
)
def test_a_url_that_does_not_answer_is_unreachable(monkeypatch, exc, reason):
    with pytest.raises(OpenApiUnreachable) as caught:
        _fetch_with(monkeypatch, exc)
    assert caught.value.reason == reason
    assert caught.value.code == "OPENAPI_UNREACHABLE"
    prompt = caught.value.error_details["handoff"]["prompt"]
    assert "https://spec.example/openapi.json" in prompt and "VPN" in prompt


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an unreachable spec URL says why")
def test_dns_and_refused_are_told_apart(monkeypatch):
    dns = httpx.ConnectError("x")
    dns.__cause__ = socket.gaierror("no such host")
    refused = httpx.ConnectError("x")
    refused.__cause__ = ConnectionRefusedError()
    assert openapi_fetch._connect_reason(dns) == "dns"
    assert openapi_fetch._connect_reason(refused) == "refused"
