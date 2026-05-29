"""Resilience of the shim's response-forwarding path.

The shim's stdout IS the MCP wire. A single non-JSON-RPC line on stdout
makes the downstream client (Claude Desktop / Cursor / Claude Code) crash
with JSONDecodeError, which is what PR #14's CI test-e2e was hitting:
the gateway returned plain "Internal Server Error" on certain failure
paths and the shim forwarded it verbatim. These tests pin the
defensive contract so the shim never crashes its client over a malformed
gateway response, regardless of root cause.
"""

from __future__ import annotations

import json

import httpx
import pytest

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.shim.main import _Bridge


@pytest.fixture
def bridge() -> _Bridge:
    info = DaemonInfo(
        version=1,
        pid=1,
        port=18000,
        token="t",
        started_at=__import__("datetime").datetime.now(
            tz=__import__("datetime").UTC,
        ),
        binary_path="/usr/bin/python3",
    )
    return _Bridge(info)


def _read_line(capsys: pytest.CaptureFixture[str]) -> str:
    out = capsys.readouterr().out.strip()
    assert out, "expected one line on stdout"
    return out


def test_forward_2xx_json_passes_through(
    bridge: _Bridge, capsys: pytest.CaptureFixture[str]
) -> None:
    envelope = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
    reply = {"jsonrpc": "2.0", "id": 7, "result": {"tools": []}}
    bridge._forward_response(envelope, httpx.Response(200, text=json.dumps(reply)))
    line = _read_line(capsys)
    assert json.loads(line) == reply


def test_forward_500_plain_text_emits_jsonrpc_error(
    bridge: _Bridge, capsys: pytest.CaptureFixture[str]
) -> None:
    envelope = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
    bridge._forward_response(envelope, httpx.Response(500, text="Internal Server Error"))
    line = _read_line(capsys)
    payload = json.loads(line)
    assert payload["id"] == 7
    assert payload["error"]["code"] == -32603
    assert "HTTP 500" in payload["error"]["message"]
    assert "Internal Server Error" in payload["error"]["message"]


def test_forward_2xx_non_json_emits_jsonrpc_error(
    bridge: _Bridge, capsys: pytest.CaptureFixture[str]
) -> None:
    envelope = {"jsonrpc": "2.0", "id": 11, "method": "initialize"}
    bridge._forward_response(envelope, httpx.Response(200, text="<html>oops</html>"))
    line = _read_line(capsys)
    payload = json.loads(line)
    assert payload["id"] == 11
    assert payload["error"]["code"] == -32603
    assert "non-JSON" in payload["error"]["message"]


def test_forward_2xx_empty_body_writes_nothing(
    bridge: _Bridge, capsys: pytest.CaptureFixture[str]
) -> None:
    envelope = {"jsonrpc": "2.0", "id": 13, "method": "notifications/initialized"}
    bridge._forward_response(envelope, httpx.Response(200, text=""))
    assert capsys.readouterr().out == ""


def test_forward_401_envelope_emits_jsonrpc_error(
    bridge: _Bridge, capsys: pytest.CaptureFixture[str]
) -> None:
    envelope = {"jsonrpc": "2.0", "id": 21, "method": "tools/list"}
    body = json.dumps({"error": {"code": "UNAUTHENTICATED", "message": "bad token"}})
    bridge._forward_response(envelope, httpx.Response(401, text=body))
    line = _read_line(capsys)
    payload = json.loads(line)
    assert payload["id"] == 21
    assert payload["error"]["code"] == -32603
    assert "HTTP 401" in payload["error"]["message"]
