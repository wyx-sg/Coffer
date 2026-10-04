"""When the shim resends a request after the daemon restarts.

`_Bridge._handle_envelope` rebinds to a restarted daemon and resends the
envelope once, unless the request may already have run: a `tools/call` whose
failure came after the send (read error, reset mid-response) is not resent,
because the old daemon may have executed it and an upstream write is not
idempotent. Driven in-process with `httpx.MockTransport`; the old daemon
listens on one port, the restarted one on another (or the same port with a
rotated token).
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

import httpx
import pytest

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.shim.main import _Bridge

_OLD_PORT = 18765
_NEW_PORT = 18766
_OLD_TOKEN = "t-old"
_NEW_TOKEN = "t-new"


def _info(port: int, token: str) -> DaemonInfo:
    return DaemonInfo(
        version=1,
        pid=12345,
        port=port,
        token=token,
        started_at=_dt.datetime.now(tz=_dt.UTC),
        binary_path="/usr/bin/python3",
    )


def _bridge() -> _Bridge:
    bridge = _Bridge(_info(_OLD_PORT, _OLD_TOKEN))
    bridge._init_envelope = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}
    return bridge


def _restart_to(monkeypatch: pytest.MonkeyPatch, port: int, token: str) -> None:
    async def _live(timeout: float) -> DaemonInfo:
        return _info(port, token)

    monkeypatch.setattr("coffer.surfaces.shim.main._wait_for_daemon", _live)


def _ok(envelope: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": envelope["id"], "result": {"ok": True}},
        headers={"Mcp-Session-Id": "s-new"},
    )


class _Daemons:
    """The old daemon fails with ``old_failure``; the new one answers.

    Records every non-initialize envelope each daemon received, so a test can
    tell whether the call reached the new daemon (was resent) or not.
    """

    def __init__(self, old_failure: Exception | None = None) -> None:
        self.old_failure = old_failure
        self.old_calls: list[str] = []
        self.new_calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        envelope = json.loads(request.content)
        on_new = (
            request.url.port == _NEW_PORT or request.headers.get("X-Coffer-Token") == _NEW_TOKEN
        )
        if not on_new:
            if isinstance(self.old_failure, httpx.ConnectError):
                raise self.old_failure
            self.old_calls.append(envelope["method"])
            if self.old_failure is not None:
                raise self.old_failure
            return httpx.Response(401, text="invalid token")
        if envelope["method"] != "initialize":
            self.new_calls.append(envelope["method"])
        return _ok(envelope)


async def _send(bridge: _Bridge, daemons: _Daemons, envelope: dict[str, Any]) -> None:
    transport = httpx.MockTransport(daemons.handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{_OLD_PORT}",
        headers={"X-Coffer-Token": _OLD_TOKEN},
    ) as client:
        await bridge._handle_envelope(client, envelope)


def _tools_call(req_id: int) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": "jira__create_issue", "arguments": {}},
    }


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool call is not re-run after the daemon restarts mid-call"
)
@pytest.mark.asyncio
async def test_tools_call_is_resent_when_connect_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A connect error means the old daemon never saw the call: resend it."""
    _restart_to(monkeypatch, _NEW_PORT, _NEW_TOKEN)
    daemons = _Daemons(old_failure=httpx.ConnectError("connection refused"))

    await _send(_bridge(), daemons, _tools_call(7))

    assert daemons.old_calls == []
    assert daemons.new_calls == ["tools/call"]
    reply = json.loads(capsys.readouterr().out.strip())
    assert reply == {"jsonrpc": "2.0", "id": 7, "result": {"ok": True}}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool call is not re-run after the daemon restarts mid-call"
)
@pytest.mark.asyncio
async def test_tools_call_is_not_resent_after_a_read_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The old daemon received the call and died before replying: it may have
    run, so the shim rebinds but answers with an error instead of resending."""
    _restart_to(monkeypatch, _NEW_PORT, _NEW_TOKEN)
    daemons = _Daemons(old_failure=httpx.ReadError("connection reset"))
    bridge = _bridge()

    await _send(bridge, daemons, _tools_call(8))

    assert daemons.old_calls == ["tools/call"]
    assert daemons.new_calls == []
    reply = json.loads(capsys.readouterr().out.strip())
    assert reply["id"] == 8
    assert reply["error"]["code"] == -32603
    assert "restarted during this tools/call" in reply["error"]["message"]
    assert "may or may not have run" in reply["error"]["message"]
    # Rebound anyway, so the next call reaches the new daemon.
    assert bridge._base == f"http://127.0.0.1:{_NEW_PORT}"
    assert bridge._session_id == "s-new"


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool call is not re-run after the daemon restarts mid-call"
)
@pytest.mark.asyncio
async def test_other_methods_are_resent_after_a_read_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Methods other than tools/call are idempotent, so a read error after the
    send is still resent to the restarted daemon."""
    _restart_to(monkeypatch, _NEW_PORT, _NEW_TOKEN)
    daemons = _Daemons(old_failure=httpx.ReadError("connection reset"))

    await _send(_bridge(), daemons, {"jsonrpc": "2.0", "id": 9, "method": "tools/list"})

    assert daemons.old_calls == ["tools/list"]
    assert daemons.new_calls == ["tools/list"]
    reply = json.loads(capsys.readouterr().out.strip())
    assert reply == {"jsonrpc": "2.0", "id": 9, "result": {"ok": True}}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool call is not re-run after the daemon restarts mid-call"
)
@pytest.mark.asyncio
async def test_tools_call_is_resent_after_a_401(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A restart on the same port rotates the token; the 401 means the call was
    rejected unrun, so it is resent with the new token."""
    _restart_to(monkeypatch, _OLD_PORT, _NEW_TOKEN)
    daemons = _Daemons()

    await _send(_bridge(), daemons, _tools_call(10))

    assert daemons.old_calls == ["tools/call"]
    assert daemons.new_calls == ["tools/call"]
    reply = json.loads(capsys.readouterr().out.strip())
    assert reply == {"jsonrpc": "2.0", "id": 10, "result": {"ok": True}}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a dropped session is answered 404 and the client handshakes again"
)
@pytest.mark.asyncio
async def test_a_dropped_session_is_handshaken_again_and_the_call_resent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The daemon's idle reaper drops a session; its next answer is 404. The shim
    replays the cached ``initialize`` (which carries the agent identity), then
    resends the call on the new session. Nothing ran, so even a tools/call is resent."""
    bridge = _bridge()
    bridge._session_id = "s-dropped"
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        envelope = json.loads(request.content)
        session = request.headers.get("Mcp-Session-Id")
        seen.append((envelope["method"], session))
        if envelope["method"] == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": envelope["id"], "result": {}},
                headers={"Mcp-Session-Id": "s-fresh"},
            )
        if session == "s-dropped":
            return httpx.Response(404, json={"error": {"message": "unknown session"}})
        return _ok(envelope)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url=f"http://127.0.0.1:{_OLD_PORT}",
        headers={"X-Coffer-Token": _OLD_TOKEN},
    ) as client:
        await bridge._handle_envelope(client, _tools_call(7))

    assert seen == [
        ("tools/call", "s-dropped"),
        ("initialize", None),
        ("tools/call", "s-fresh"),
    ]
    assert bridge._session_id != "s-dropped"
    assert '"ok":true' in capsys.readouterr().out
