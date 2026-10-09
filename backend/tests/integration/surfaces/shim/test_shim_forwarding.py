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
from coffer.surfaces.shim.wire import forward_response


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
    forward_response(envelope, httpx.Response(200, text=json.dumps(reply)))
    line = _read_line(capsys)
    assert json.loads(line) == reply


def test_forward_500_plain_text_emits_jsonrpc_error(
    bridge: _Bridge, capsys: pytest.CaptureFixture[str]
) -> None:
    envelope = {"jsonrpc": "2.0", "id": 7, "method": "tools/list"}
    forward_response(envelope, httpx.Response(500, text="Internal Server Error"))
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
    forward_response(envelope, httpx.Response(200, text="<html>oops</html>"))
    line = _read_line(capsys)
    payload = json.loads(line)
    assert payload["id"] == 11
    assert payload["error"]["code"] == -32603
    assert "non-JSON" in payload["error"]["message"]


def test_forward_2xx_empty_body_writes_nothing(
    bridge: _Bridge, capsys: pytest.CaptureFixture[str]
) -> None:
    envelope = {"jsonrpc": "2.0", "id": 13, "method": "notifications/initialized"}
    forward_response(envelope, httpx.Response(200, text=""))
    assert capsys.readouterr().out == ""


def test_forward_401_envelope_emits_jsonrpc_error(
    bridge: _Bridge, capsys: pytest.CaptureFixture[str]
) -> None:
    envelope = {"jsonrpc": "2.0", "id": 21, "method": "tools/list"}
    body = json.dumps({"error": {"code": "UNAUTHENTICATED", "message": "bad token"}})
    forward_response(envelope, httpx.Response(401, text=body))
    line = _read_line(capsys)
    payload = json.loads(line)
    assert payload["id"] == 21
    assert payload["error"]["code"] == -32603
    assert "HTTP 401" in payload["error"]["message"]


def test_a_refusal_reaches_the_agent_with_its_message_and_handoff(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A daemon waiting for git refuses ``/mcp`` with the setup message and the
    hand-off (spec daemon "Wait in a setup state when git is missing or too
    old"): the agent is told both, whole, not the body's first 200 bytes."""
    prompt = "Please install git on this machine.\n" + "x" * 400
    body = {
        "error": {
            "code": "GIT_NEEDED",
            "message": "Coffer needs git, and git isn't installed on this machine.",
            "details": {"reason": "git_missing", "handoff": {"prompt": prompt}},
        }
    }
    envelope = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    forward_response(envelope, httpx.Response(503, text=json.dumps(body)))
    message = json.loads(_read_line(capsys))["error"]["message"]
    assert message.startswith("coffer gateway HTTP 503: Coffer needs git")
    assert message.endswith(prompt)
