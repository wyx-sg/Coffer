"""In-process coverage for _Bridge._pump_stdin and _Bridge._drain_sse (TEST-017).

The shim subprocess tests in test_shim.py spawn `coffer-mcp-shim` end-to-end,
which doesn't actually exercise the in-process functions for coverage. These
tests instantiate the `_Bridge` class directly and drive each pump with a
fake httpx transport (`httpx.MockTransport`) + an `asyncio.StreamReader`
substituted for the real stdin pipe.

We patch `connect_read_pipe` to wire our pre-fed `StreamReader` directly
into `_pump_stdin`, since asyncio refuses to attach a pipe to a non-file-
descriptor backed object on most platforms.

Goal: lift `surfaces/shim/main.py` from 41% file coverage to ≥85%.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import sys
from typing import Any

import httpx
import pytest

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.shim.main import _Bridge


def _make_bridge(port: int = 18765) -> _Bridge:
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=port,
        token="t-internals",
        started_at=_dt.datetime.now(tz=_dt.UTC),
        binary_path="/usr/bin/python3",
    )
    return _Bridge(info)


def _patch_pump_stdin_with_reader(
    monkeypatch: pytest.MonkeyPatch, reader: asyncio.StreamReader
) -> None:
    """Make _pump_stdin's `connect_read_pipe` return our prefed reader.

    asyncio.connect_read_pipe needs a real fd; we monkeypatch the loop's
    method so the StreamReaderProtocol it gets handed is wired to our
    StreamReader.  In practice it is simpler to replace get_event_loop()
    so the .connect_read_pipe call is a no-op and a closure over `reader`
    is what gets exposed.  We do that by patching asyncio.StreamReader so
    that the instance _Bridge constructs is replaced by ours.
    """
    real_stream_reader_cls = asyncio.StreamReader

    class _PrefedReaderShim(real_stream_reader_cls):  # type: ignore[misc, valid-type]
        def __new__(cls, *args: Any, **kwargs: Any) -> asyncio.StreamReader:
            return reader

    monkeypatch.setattr("coffer.surfaces.shim.main.asyncio.StreamReader", _PrefedReaderShim)

    async def _noop_connect_read_pipe(_protocol_factory: Any, _pipe: Any) -> tuple[Any, Any]:
        return (None, None)

    loop = asyncio.get_event_loop()
    monkeypatch.setattr(loop, "connect_read_pipe", _noop_connect_read_pipe)


# --------------------------------------------------------------------------- #
# _pump_stdin                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pump_stdin_forwards_post_and_captures_session_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A well-formed envelope on stdin is POSTed to /mcp; the response's
    Mcp-Session-Id header is captured for subsequent requests; the body is
    written to stdout."""
    bridge = _make_bridge()

    posted: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(
            {
                "url": str(request.url),
                "headers": dict(request.headers),
                "body": json.loads(request.content.decode("utf-8")),
            }
        )
        body = json.dumps(
            {"jsonrpc": "2.0", "id": posted[-1]["body"]["id"], "result": {"ok": True}}
        )
        return httpx.Response(
            200,
            text=body,
            headers={"Mcp-Session-Id": "sess-abc123"},
        )

    reader = asyncio.StreamReader()
    envelope = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    reader.feed_data((json.dumps(envelope) + "\n").encode("utf-8"))
    reader.feed_eof()
    _patch_pump_stdin_with_reader(monkeypatch, reader)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        await bridge._pump_stdin(client)

    # POST was forwarded to /mcp with the envelope intact
    assert len(posted) == 1
    assert posted[0]["url"].endswith("/mcp")
    assert posted[0]["body"] == envelope

    # Session id was captured on the bridge
    assert bridge._session_id == "sess-abc123"

    # stdin EOF caused the bridge to request shutdown
    assert bridge._stop.is_set()

    # The successful 200 JSON response was written to stdout
    out = capsys.readouterr().out.strip()
    line = json.loads(out)
    assert line["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_pump_stdin_skips_bad_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A line that is not valid JSON is logged + skipped, NOT forwarded.

    Asserts the `shim.bad_json_from_stdin` branch (line 159 in main.py).
    """
    bridge = _make_bridge()
    posted: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(request)
        return httpx.Response(200, text='{"jsonrpc":"2.0","id":1,"result":{}}')

    reader = asyncio.StreamReader()
    # First line: malformed JSON
    reader.feed_data(b"this is not json\n")
    # Second line: well-formed envelope
    reader.feed_data(
        (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n").encode("utf-8")
    )
    reader.feed_eof()
    _patch_pump_stdin_with_reader(monkeypatch, reader)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        await bridge._pump_stdin(client)

    # Only the second (valid) line resulted in a POST
    assert len(posted) == 1


@pytest.mark.asyncio
async def test_pump_stdin_post_failure_emits_jsonrpc_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the HTTP POST raises, the shim writes a JSON-RPC error envelope
    bound to the request id (the `shim.post_failed` branch, lines 178-187).
    """
    bridge = _make_bridge()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection refused")

    reader = asyncio.StreamReader()
    reader.feed_data(
        (json.dumps({"jsonrpc": "2.0", "id": 42, "method": "tools/list"}) + "\n").encode("utf-8")
    )
    reader.feed_eof()
    _patch_pump_stdin_with_reader(monkeypatch, reader)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        await bridge._pump_stdin(client)

    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["id"] == 42
    assert payload["error"]["code"] == -32603
    assert "shim:" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_pump_stdin_attaches_session_header_on_subsequent_requests(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """After the first response carries Mcp-Session-Id, the next POST attaches
    that header (lines 168-169).  Drives two envelopes through the pump."""
    bridge = _make_bridge()
    seen_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(request.headers))
        body = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            text=json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {}}),
            headers={"Mcp-Session-Id": "sess-xyz"},
        )

    reader = asyncio.StreamReader()
    for i in (1, 2):
        reader.feed_data(
            (json.dumps({"jsonrpc": "2.0", "id": i, "method": "tools/list"}) + "\n").encode("utf-8")
        )
    reader.feed_eof()
    _patch_pump_stdin_with_reader(monkeypatch, reader)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        await bridge._pump_stdin(client)

    assert len(seen_headers) == 2
    # First request had no Mcp-Session-Id; second one did.
    assert "mcp-session-id" not in {k.lower() for k in seen_headers[0]}
    assert seen_headers[1].get("mcp-session-id") == "sess-xyz"


# --------------------------------------------------------------------------- #
# _drain_sse                                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_drain_sse_forwards_payloads_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each SSE data: line whose payload is non-empty is written to stdout."""
    bridge = _make_bridge()
    bridge._session_id = "sess-1"

    sse_body = (
        "data: " + json.dumps({"a": 1}) + "\n"
        ":heartbeat\n"
        "data: " + json.dumps({"b": 2}) + "\n"
        "data: \n"  # empty data — must be skipped
        "data: " + json.dumps({"c": 3}) + "\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Mcp-Session-Id") == "sess-1"
        return httpx.Response(
            200,
            text=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        # Single connection attempt (the reconnect wrapper is tested separately).
        assert await bridge._drain_sse_once(client) is True

    lines = [line for line in capsys.readouterr().out.split("\n") if line]
    payloads = [json.loads(line) for line in lines]
    assert {"a": 1} in payloads
    assert {"b": 2} in payloads
    assert {"c": 3} in payloads


@pytest.mark.asyncio
async def test_drain_sse_non_200_returns_without_writing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-200 SSE response is logged + dropped (the `shim.sse_unexpected_status`
    branch).  Nothing is written to stdout."""
    bridge = _make_bridge()
    bridge._session_id = "sess-1"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream busy")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        assert await bridge._drain_sse_once(client) is False

    assert capsys.readouterr().out == ""


@pytest.mark.asyncio
async def test_drain_sse_exits_when_stop_set_before_session_id() -> None:
    """If stop is set before a session id is known, _drain_sse returns
    promptly without ever opening a stream (covers the early-return branch
    around line 252-253)."""
    bridge = _make_bridge()
    bridge.stop()  # set _stop before drain runs

    # No handler should be reached — assert via empty call count.
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="data: {}\n")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        await asyncio.wait_for(bridge._drain_sse(client), timeout=2.0)

    assert calls == 0


@pytest.mark.asyncio
async def test_drain_sse_ignores_non_data_lines(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Lines that don't begin with `data:` (event:/id:/blanks) are skipped
    (line 266 `continue` branch)."""
    bridge = _make_bridge()
    bridge._session_id = "sess-only-comment"

    sse_body = ":heartbeat 1\nevent: ping\nid: 17\n\ndata: " + json.dumps({"ok": True}) + "\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        assert await bridge._drain_sse_once(client) is True

    lines = [line for line in capsys.readouterr().out.split("\n") if line]
    assert lines == [json.dumps({"ok": True})]


@pytest.mark.asyncio
async def test_drain_sse_stops_mid_stream_when_bridge_stopped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """While iterating the SSE stream, if `_stop` is set the inner break path
    is taken (covers the `while not self._stop.is_set()` branch on line 251).
    """
    bridge = _make_bridge()
    bridge._session_id = "sess-mid"

    def handler(request: httpx.Request) -> httpx.Response:
        # Long stream — drain_sse must stop as soon as _stop is set.
        body = 'data: {"i":1}\ndata: {"i":2}\ndata: {"i":3}\n'
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:

        async def _runner() -> None:
            await bridge._drain_sse(client)

        task = asyncio.create_task(_runner())
        await asyncio.sleep(0)
        bridge.stop()
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_drain_sse_reconnects_after_stream_ends(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CODE-046: when an SSE stream ends (e.g. the daemon reaped the session),
    _drain_sse must reconnect rather than stop forwarding for good. We count
    GET attempts and stop the bridge once it has reconnected at least once."""
    bridge = _make_bridge()
    bridge._session_id = "sess-reconnect"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls >= 2:
            bridge.stop()  # let the reconnect loop terminate
        return httpx.Response(200, text=f'data: {{"n": {calls}}}\n')

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        await asyncio.wait_for(bridge._drain_sse(client), timeout=5.0)

    assert calls >= 2, "drain_sse must reconnect after the first stream ends"
    payloads = [json.loads(line) for line in capsys.readouterr().out.split("\n") if line]
    assert {"n": 1} in payloads


# --------------------------------------------------------------------------- #
# top-level helpers: _setup_shim_log + _spawn_daemon + _ensure_daemon + run()  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_setup_shim_log_creates_handler(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_setup_shim_log adds a FileHandler under ~/.coffer/logs (lines 41-50)."""
    from coffer.surfaces.shim import main as shim_main

    monkeypatch.setattr(shim_main, "_SHIM_LOG_DIR", tmp_path / "logs")
    # Reset handlers between runs so the assertion is meaningful.
    shim_main._logger.handlers.clear()
    shim_main._setup_shim_log()
    assert any(isinstance(h, __import__("logging").FileHandler) for h in shim_main._logger.handlers)
    # The log file lives under our patched dir.
    log_files = list((tmp_path / "logs").glob("shim-*.log"))
    assert log_files, "expected a shim-*.log file to be created"


@pytest.mark.asyncio
async def test_setup_shim_log_swallows_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """If mkdir raises OSError, _setup_shim_log silently continues (line 48-50)."""
    from coffer.surfaces.shim import main as shim_main

    class _BadPath:
        def mkdir(self, *args: Any, **kwargs: Any) -> None:
            raise OSError("simulated permission denied")

        def __truediv__(self, _other: Any) -> _BadPath:
            return self

    monkeypatch.setattr(shim_main, "_SHIM_LOG_DIR", _BadPath())
    # Should NOT raise.
    shim_main._setup_shim_log()


@pytest.mark.asyncio
async def test_spawn_daemon_invokes_popen(monkeypatch: pytest.MonkeyPatch) -> None:
    """_spawn_daemon runs subprocess.Popen with start_new_session on POSIX
    (or CREATE_NO_WINDOW|DETACHED_PROCESS on Windows). Covers lines 74-90."""
    from coffer.surfaces.shim import main as shim_main

    invoked: list[dict[str, Any]] = []

    def _fake_popen(cmd: list[str], **kwargs: Any) -> object:
        invoked.append({"cmd": cmd, "kwargs": kwargs})

        class _P:
            pid = 12345

        return _P()

    monkeypatch.setattr(shim_main.subprocess, "Popen", _fake_popen)
    shim_main._spawn_daemon()

    assert len(invoked) == 1
    assert invoked[0]["cmd"][1:] == [
        "-m",
        "coffer.surfaces.cli.main",
        "daemon",
        "start",
    ]
    if sys.platform != "win32":
        assert invoked[0]["kwargs"].get("start_new_session") is True


@pytest.mark.asyncio
async def test_spawn_daemon_logs_and_writes_stderr_on_oserror(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Popen raising OSError is caught and reported to stderr (lines 88-90)."""
    from coffer.surfaces.shim import main as shim_main

    def _bad_popen(cmd: list[str], **kwargs: Any) -> object:
        raise OSError("simulated spawn failure")

    monkeypatch.setattr(shim_main.subprocess, "Popen", _bad_popen)
    shim_main._spawn_daemon()
    err = capsys.readouterr().err
    assert "failed to spawn daemon" in err


@pytest.mark.asyncio
async def test_wait_for_daemon_returns_none_when_status_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If discover() returns a DaemonInfo but /daemon/status raises, the loop
    keeps polling until the deadline lapses (covers the exception branch on
    lines 66-67).  Use a small timeout so the test finishes promptly."""
    from coffer.surfaces.shim import main as shim_main

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=18999,
        token="t",
        started_at=_dt.datetime.now(tz=_dt.UTC),
        binary_path="/usr/bin/python3",
    )
    monkeypatch.setattr(shim_main, "discover", lambda: info)

    class _BadClient:
        async def __aenter__(self) -> _BadClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, *args: Any, **kwargs: Any) -> Any:
            raise httpx.ConnectError("nope")

    def _bad_async_client(*args: Any, **kwargs: Any) -> _BadClient:
        return _BadClient()

    monkeypatch.setattr(shim_main.httpx, "AsyncClient", _bad_async_client)
    result = await shim_main._wait_for_daemon(timeout=0.3)
    assert result is None


@pytest.mark.asyncio
async def test_wait_for_daemon_returns_info_on_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy-path: discover returns info AND /daemon/status returns 200."""
    from coffer.surfaces.shim import main as shim_main

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=18999,
        token="t",
        started_at=_dt.datetime.now(tz=_dt.UTC),
        binary_path="/usr/bin/python3",
    )
    monkeypatch.setattr(shim_main, "discover", lambda: info)

    class _OkClient:
        async def __aenter__(self) -> _OkClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, *args: Any, **kwargs: Any) -> httpx.Response:
            return httpx.Response(200, text='{"status":"ready"}')

    monkeypatch.setattr(shim_main.httpx, "AsyncClient", lambda *a, **kw: _OkClient())
    result = await shim_main._wait_for_daemon(timeout=2.0)
    assert result is info


@pytest.mark.asyncio
async def test_ensure_daemon_exits_when_spawn_does_not_come_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If _spawn_daemon doesn't bring the daemon up, the shim exits with
    code 3 (lines 100-104)."""
    from coffer.surfaces.shim import main as shim_main

    async def _never(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(shim_main, "_wait_for_daemon", _never)
    monkeypatch.setattr(shim_main, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(shim_main, "_DAEMON_BOOT_TIMEOUT", 0)

    with pytest.raises(SystemExit) as excinfo:
        await shim_main._ensure_daemon()
    assert excinfo.value.code == 3


def test_run_handles_keyboard_interrupt_with_code_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() wraps _async_main and converts KeyboardInterrupt to exit-code 0
    (lines 294-303)."""
    from coffer.surfaces.shim import main as shim_main

    def _raise(coro: Any = None, *args: Any, **kwargs: Any) -> None:
        # asyncio.run is called as asyncio.run(_async_main()); the coroutine
        # passed in must be closed so Python doesn't emit a RuntimeWarning.
        if coro is not None and hasattr(coro, "close"):
            coro.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(shim_main.asyncio, "run", _raise)
    with pytest.raises(SystemExit) as excinfo:
        shim_main.run()
    assert excinfo.value.code == 0


def test_run_handles_unexpected_exception_with_code_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Uncaught Exception inside _async_main → exit 1 + stderr explanation."""
    from coffer.surfaces.shim import main as shim_main

    def _raise(coro: Any = None, *args: Any, **kwargs: Any) -> None:
        # asyncio.run is called as asyncio.run(_async_main()); the coroutine
        # passed in must be closed so Python doesn't emit a RuntimeWarning.
        if coro is not None and hasattr(coro, "close"):
            coro.close()
        raise RuntimeError("boom")

    monkeypatch.setattr(shim_main.asyncio, "run", _raise)
    with pytest.raises(SystemExit) as excinfo:
        shim_main.run()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "fatal" in err


def test_run_propagates_system_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """SystemExit raised from inside _async_main keeps the original exit code."""
    from coffer.surfaces.shim import main as shim_main

    def _raise(coro: Any = None, *args: Any, **kwargs: Any) -> None:
        # asyncio.run is called as asyncio.run(_async_main()); the coroutine
        # passed in must be closed so Python doesn't emit a RuntimeWarning.
        if coro is not None and hasattr(coro, "close"):
            coro.close()
        raise SystemExit(7)

    monkeypatch.setattr(shim_main.asyncio, "run", _raise)
    with pytest.raises(SystemExit) as excinfo:
        shim_main.run()
    assert excinfo.value.code == 7


@pytest.mark.asyncio
async def test_bridge_run_stops_when_stop_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_Bridge.run wires up stdin + sse tasks and exits when stop is set
    (covers lines 121-136)."""
    bridge = _make_bridge()

    async def _no_stdin(client: httpx.AsyncClient) -> None:
        # Block forever until cancelled.
        await asyncio.Event().wait()

    async def _no_sse(client: httpx.AsyncClient) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(bridge, "_pump_stdin", _no_stdin)
    monkeypatch.setattr(bridge, "_drain_sse", _no_sse)

    async def _trigger_stop() -> None:
        await asyncio.sleep(0.05)
        bridge.stop()

    asyncio.create_task(_trigger_stop())  # noqa: RUF006
    rc = await asyncio.wait_for(bridge.run(), timeout=3.0)
    assert rc == 0


@pytest.mark.asyncio
async def test_pump_stdin_treats_connection_reset_as_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ConnectionResetError raised from `readline()` ends the pump cleanly
    (covers lines 149-150)."""
    bridge = _make_bridge()

    class _ResettingReader(asyncio.StreamReader):
        async def readline(self) -> bytes:
            raise ConnectionResetError("simulated pipe reset")

    reader = _ResettingReader()

    real_stream_reader_cls = asyncio.StreamReader

    class _ResetStreamReaderShim(real_stream_reader_cls):  # type: ignore[misc, valid-type]
        def __new__(cls, *args: Any, **kwargs: Any) -> Any:
            return reader

    monkeypatch.setattr("coffer.surfaces.shim.main.asyncio.StreamReader", _ResetStreamReaderShim)

    async def _noop_connect_read_pipe(_protocol_factory: Any, _pipe: Any) -> tuple[Any, Any]:
        return (None, None)

    loop = asyncio.get_event_loop()
    monkeypatch.setattr(loop, "connect_read_pipe", _noop_connect_read_pipe)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
        base_url="http://127.0.0.1:18765",
    ) as client:
        # Should NOT raise; should exit cleanly on the reset.
        await asyncio.wait_for(bridge._pump_stdin(client), timeout=2.0)


@pytest.mark.asyncio
async def test_drain_sse_swallows_stream_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A connection error mid-stream is caught (the `shim.sse_disconnected`
    branch around line 273-274) and does not propagate.
    """
    bridge = _make_bridge()
    bridge._session_id = "sess-err"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("simulated read error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:18765") as client:
        # Should NOT raise; one attempt returns False so the loop would back off.
        assert await bridge._drain_sse_once(client) is False

    # No payloads written
    assert capsys.readouterr().out == ""
