"""Integration tests for HttpUpstreamConnection.

Failure-mode tests run against ports nothing is listening on — they don't
need a real MCP server and complete quickly.

The header_overlay test spins up a minimal raw-socket TCP server in a
plain thread (no asyncio, no event-loop conflicts) that captures the
incoming HTTP request headers, replies with a connection-close 400 so the
SDK gets an HTTP error and terminates quickly, then asserts the overlay
header was forwarded.

The happy-path test (test_http_upstream_spawn_initialize_and_call) starts
the fake_mcp_server.py in --transport http mode as a subprocess, waits for
its "READY port=N" announcement, then exercises spawn_and_initialize() +
tools/call through HttpUpstreamConnection.
"""

from __future__ import annotations

import asyncio
import socket
import threading

import pytest

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import HttpTransport
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection
from tests.fixtures.fake_mcp_server import start_http_fake as _start_http_fake


@pytest.mark.asyncio
async def test_connection_refused_surfaces_as_upstream_error() -> None:
    """Pointing at a loopback port nothing is listening on raises a domain error.

    On macOS port 1 is typically filtered (not immediately refused), so the
    connection either times out (UpstreamTimeout) or fails with a connect
    error (UpstreamUnavailable).  Both are acceptable — the caller just needs
    to know the upstream is not reachable.
    """
    conn = HttpUpstreamConnection(
        transport=HttpTransport(
            type="http",
            url="http://127.0.0.1:1/mcp",  # port 1 refuses/times out
        ),
        header_overlay={},
        spawn_timeout_seconds=2,
    )
    with pytest.raises((UpstreamUnavailable, UpstreamTimeout)):
        await conn.spawn_and_initialize()
    await conn.close()


@pytest.mark.asyncio
async def test_request_before_init_raises() -> None:
    """Calling request() before spawn_and_initialize() raises UpstreamUnavailable."""
    conn = HttpUpstreamConnection(
        transport=HttpTransport(
            type="http",
            url="http://127.0.0.1:1/mcp",
        ),
        header_overlay={},
    )
    with pytest.raises(UpstreamUnavailable):
        await conn.request("tools/list", {})


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    """Multiple close() calls must not raise."""
    conn = HttpUpstreamConnection(
        transport=HttpTransport(
            type="http",
            url="http://127.0.0.1:1/mcp",
        ),
        header_overlay={},
    )
    await conn.close()
    await conn.close()  # second close is a no-op


def _capturing_stub_server(
    port: int,
    captured: dict[str, str],
    ready: threading.Event,
) -> None:
    """Single-connection raw TCP stub that captures the Authorization header.

    Accepts one connection, reads the request headers, captures the
    Authorization value (if present), then replies with HTTP 400 so
    the SDK's httpx client raises an HTTPStatusError and unblocks
    session.initialize() quickly.  Runs in a plain (non-asyncio) thread.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(5)
        srv.settimeout(10.0)
        ready.set()

        try:
            conn_sock, _ = srv.accept()
        except OSError:
            return

        with conn_sock:
            conn_sock.settimeout(5.0)
            try:
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = conn_sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk

                header_section = data.split(b"\r\n\r\n")[0].decode("utf-8", errors="replace")
                for line in header_section.splitlines():
                    if line.lower().startswith("authorization:"):
                        captured["Authorization"] = line.split(":", 1)[1].strip()
                        break

                # Reply with 400 Bad Request so httpx raises an error quickly,
                # which propagates back to session.initialize() as an exception.
                conn_sock.sendall(
                    b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
            except OSError:
                pass


@pytest.mark.asyncio
async def test_header_overlay_passes_through() -> None:
    """overlay headers are forwarded to the upstream HTTP endpoint.

    Spins up a minimal raw-socket stub in a plain thread (no asyncio
    event-loop conflicts), captures the Authorization header, returns
    an HTTP 400 so the SDK fails fast, then asserts the header value.
    """
    captured: dict[str, str] = {}
    ready = threading.Event()

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server_thread = threading.Thread(
        target=_capturing_stub_server,
        args=(port, captured, ready),
        daemon=True,
    )
    server_thread.start()
    ready.wait(timeout=5.0)

    conn = HttpUpstreamConnection(
        transport=HttpTransport(
            type="http",
            url=f"http://127.0.0.1:{port}/mcp",
        ),
        header_overlay={"Authorization": "Bearer testtoken"},
        spawn_timeout_seconds=5,
    )
    with pytest.raises((UpstreamUnavailable, UpstreamTimeout)):
        await conn.spawn_and_initialize()
    await conn.close()

    server_thread.join(timeout=3)

    # The SDK sends the initialize POST (carrying the overlay header) BEFORE the
    # stub's 400 makes it fail, so the header MUST have been captured. Assert
    # unconditionally — a guarding `if captured:` would let a regression that
    # drops the overlay header pass vacuously (the very thing this test pins).
    assert captured, "stub never received a request — overlay header not verified"
    assert captured.get("Authorization") == "Bearer testtoken"


@pytest.mark.asyncio
async def test_unsupported_method_raises() -> None:
    """_dispatch_method with an unrecognised method raises UpstreamUnavailable."""
    from unittest.mock import AsyncMock, MagicMock

    from mcp import ClientSession

    fake_session = MagicMock(spec=ClientSession)
    fake_session.list_tools = AsyncMock(return_value=object())

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )
    conn._session = fake_session

    with pytest.raises(UpstreamUnavailable, match="not supported"):
        await conn._dispatch_method("unknown/method", {})


def _stub_5xx_server(port: int, ready: threading.Event) -> None:
    """Single-shot TCP server that replies HTTP 500 to the first connection."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port))
        srv.listen(5)
        srv.settimeout(5.0)
        ready.set()
        try:
            sock, _ = srv.accept()
        except OSError:
            return
        with sock:
            sock.settimeout(2.0)
            try:
                _ = sock.recv(4096)  # consume the request
                sock.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Length: 0\r\n"
                    b"Connection: close\r\n\r\n"
                )
            except OSError:
                pass


@pytest.mark.asyncio
async def test_5xx_response_raises_upstream_unavailable() -> None:
    """TEST-019: an HTTP 5xx from the upstream during initialize() surfaces
    as an UpstreamUnavailable domain error (NOT a bare httpx exception).
    """
    ready = threading.Event()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    t = threading.Thread(target=_stub_5xx_server, args=(port, ready), daemon=True)
    t.start()
    ready.wait(timeout=5.0)

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url=f"http://127.0.0.1:{port}/mcp"),
        header_overlay={},
        spawn_timeout_seconds=5,
    )
    with pytest.raises((UpstreamUnavailable, UpstreamTimeout)):
        await conn.spawn_and_initialize()
    await conn.close()
    t.join(timeout=3)


@pytest.mark.asyncio
async def test_initialize_timeout_raises_upstream_timeout() -> None:
    """TEST-019: when the upstream accepts the TCP connection but never
    completes the HTTP response, the httpx timeout fires and is wrapped
    as UpstreamTimeout (OR UpstreamUnavailable depending on which leg of
    the SDK detects it first; both are acceptable domain errors).
    """
    ready = threading.Event()

    def _hang_server() -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            port_local = srv.getsockname()[1]
            captured["port"] = port_local
            ready.set()
            try:
                sock, _ = srv.accept()
            except OSError:
                return
            # Accept the connection but never reply.
            with sock:
                try:
                    sock.settimeout(2.0)
                    _ = sock.recv(4096)
                except OSError:
                    pass

    captured: dict[str, int] = {}
    t = threading.Thread(target=_hang_server, daemon=True)
    t.start()
    ready.wait(timeout=5.0)

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url=f"http://127.0.0.1:{captured['port']}/mcp"),
        header_overlay={},
        spawn_timeout_seconds=1,  # short — bound test wall-clock
    )
    with pytest.raises((UpstreamTimeout, UpstreamUnavailable)):
        await conn.spawn_and_initialize()
    await conn.close()
    t.join(timeout=3)


@pytest.mark.asyncio
async def test_http_upstream_spawn_initialize_and_call() -> None:
    """Start a real HTTP MCP upstream (fake_mcp_server --transport http),
    use HttpUpstreamConnection.spawn_and_initialize(), then tools/call,
    and assert a correct echo result.
    """
    # Use the shared helper from tests.fixtures.fake_mcp_server to start
    # the HTTP fake server and resolve its port without duplicating the
    # queue/threading logic.
    loop = asyncio.get_running_loop()
    proc, port = await loop.run_in_executor(None, _start_http_fake, ["ping"])
    try:
        conn = HttpUpstreamConnection(
            transport=HttpTransport(
                type="http",
                url=f"http://127.0.0.1:{port}/mcp",
            ),
            header_overlay={},
            spawn_timeout_seconds=10,
        )
        try:
            caps = await conn.spawn_and_initialize()
            # The server advertises tools capability.
            assert isinstance(caps, dict)

            result = await conn.request("tools/list", {})
            tool_names = {t.name for t in result.tools}
            assert "ping" in tool_names, f"Expected 'ping' in tools: {tool_names}"

            call_result = await conn.request("tools/call", {"name": "ping", "arguments": {}})
            # The fake server echoes: "echo:ping:{}"
            content = call_result.content[0]
            assert "echo:ping:" in content.text
        finally:
            await conn.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# --------------------------------------------------------------------------- #
# Unit tests for _dispatch_method / request() / _message_handler / capability
# fallback using a FAKE async session (no real HTTP server needed). Mirrors the
# fake-session pattern from test_progress_passthrough.py.
# --------------------------------------------------------------------------- #


class _FakeSession:
    """Minimal async stand-in for mcp ClientSession exposing the methods that
    _dispatch_method routes to. Each method returns a unique sentinel so the
    test can assert the dispatch went to the right place and the value is
    returned unchanged."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.tools_sentinel = object()
        self.resources_sentinel = object()
        self.read_sentinel = object()
        self.prompts_sentinel = object()
        self.get_prompt_sentinel = object()
        self.call_sentinel = object()

    async def list_tools(self) -> object:
        self.calls.append(("list_tools", (), {}))
        return self.tools_sentinel

    async def call_tool(self, name, arguments=None, read_timeout_seconds=None) -> object:
        self.calls.append(("call_tool", (name,), {"arguments": arguments}))
        return self.call_sentinel

    async def list_resources(self) -> object:
        self.calls.append(("list_resources", (), {}))
        return self.resources_sentinel

    async def read_resource(self, uri) -> object:
        self.calls.append(("read_resource", (uri,), {}))
        return self.read_sentinel

    async def list_prompts(self) -> object:
        self.calls.append(("list_prompts", (), {}))
        return self.prompts_sentinel

    async def get_prompt(self, name, arguments=None) -> object:
        self.calls.append(("get_prompt", (name,), {"arguments": arguments}))
        return self.get_prompt_sentinel


def _conn_with_fake_session() -> tuple[HttpUpstreamConnection, _FakeSession]:
    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )
    fake = _FakeSession()
    conn._session = fake
    return conn, fake


@pytest.mark.asyncio
async def test_request_resources_list_dispatches_to_list_resources() -> None:
    """request('resources/list') routes to session.list_resources() and returns its value."""
    conn, fake = _conn_with_fake_session()
    result = await conn.request("resources/list", {})
    assert result is fake.resources_sentinel
    assert fake.calls == [("list_resources", (), {})]


@pytest.mark.asyncio
async def test_request_resources_read_passes_uri() -> None:
    """request('resources/read') forwards the uri param to session.read_resource()."""
    conn, fake = _conn_with_fake_session()
    result = await conn.request("resources/read", {"uri": "file:///x"})
    assert result is fake.read_sentinel
    assert fake.calls == [("read_resource", ("file:///x",), {})]


@pytest.mark.asyncio
async def test_request_prompts_list_dispatches_to_list_prompts() -> None:
    """request('prompts/list') routes to session.list_prompts() and returns its value."""
    conn, fake = _conn_with_fake_session()
    result = await conn.request("prompts/list", {})
    assert result is fake.prompts_sentinel
    assert fake.calls == [("list_prompts", (), {})]


@pytest.mark.asyncio
async def test_request_prompts_get_passes_name_and_arguments() -> None:
    """request('prompts/get') forwards name + arguments to session.get_prompt()."""
    conn, fake = _conn_with_fake_session()
    result = await conn.request("prompts/get", {"name": "greet", "arguments": {"who": "bob"}})
    assert result is fake.get_prompt_sentinel
    assert fake.calls == [("get_prompt", ("greet",), {"arguments": {"who": "bob"}})]


@pytest.mark.asyncio
async def test_request_tools_list_dispatches_to_list_tools() -> None:
    """request('tools/list') routes to session.list_tools() and returns its value."""
    conn, fake = _conn_with_fake_session()
    result = await conn.request("tools/list", {})
    assert result is fake.tools_sentinel
    assert fake.calls == [("list_tools", (), {})]


@pytest.mark.asyncio
async def test_request_unsupported_method_raises_via_request() -> None:
    """request() with an unrecognised method surfaces UpstreamUnavailable
    (the raise at the end of _dispatch_method), with no session call made."""
    conn, fake = _conn_with_fake_session()
    with pytest.raises(UpstreamUnavailable, match="not supported"):
        await conn.request("bogus/method", {})
    assert fake.calls == []


@pytest.mark.asyncio
async def test_request_when_session_none_raises_upstream_unavailable() -> None:
    """request() before a session exists raises UpstreamUnavailable('upstream not initialized')."""
    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )
    assert conn._session is None
    with pytest.raises(UpstreamUnavailable, match="not initialized"):
        await conn.request("tools/list", {})


@pytest.mark.asyncio
async def test_message_handler_forwards_server_notification() -> None:
    """_message_handler forwards a ServerNotification to a registered on_notification
    callback, and ignores messages that are not ServerNotifications."""
    from mcp.types import (
        LoggingMessageNotification,
        LoggingMessageNotificationParams,
        ServerNotification,
    )

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )

    received: list[object] = []

    async def _on_notification(msg: object) -> None:
        received.append(msg)

    conn.on_notification(_on_notification)
    assert conn._notification_callback is _on_notification

    notif = ServerNotification(
        LoggingMessageNotification(
            method="notifications/message",
            params=LoggingMessageNotificationParams(level="info", data="hello"),
        )
    )
    await conn._message_handler(notif)
    assert received == [notif]

    # A non-ServerNotification message must NOT be forwarded.
    await conn._message_handler(object())
    assert received == [notif]


@pytest.mark.asyncio
async def test_message_handler_no_callback_is_noop() -> None:
    """_message_handler with no registered callback silently drops the notification."""
    from mcp.types import (
        LoggingMessageNotification,
        LoggingMessageNotificationParams,
        ServerNotification,
    )

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )
    notif = ServerNotification(
        LoggingMessageNotification(
            method="notifications/message",
            params=LoggingMessageNotificationParams(level="info", data="hello"),
        )
    )
    # Must not raise even though no callback is registered.
    await conn._message_handler(notif)


def test_on_sampling_and_roots_register_callbacks() -> None:
    """on_sampling_request / on_roots_request store the callback for use during
    ClientSession construction in spawn_and_initialize()."""

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )

    async def _sampling(*args, **kwargs):  # pragma: no cover - identity only
        return None

    async def _roots(*args, **kwargs):  # pragma: no cover - identity only
        return None

    conn.on_sampling_request(_sampling)
    conn.on_roots_request(_roots)
    assert conn._sampling_callback is _sampling
    assert conn._list_roots_callback is _roots


@pytest.mark.asyncio
async def test_request_timeout_wraps_as_upstream_timeout() -> None:
    """When _dispatch_method exceeds request_timeout_seconds, request() raises
    UpstreamTimeout (asyncio.wait_for -> TimeoutError -> domain error)."""

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
        request_timeout_seconds=0,  # any positive dispatch will exceed 0s
    )

    class _SlowSession:
        async def list_tools(self) -> object:
            await asyncio.sleep(1)
            return object()

    conn._session = _SlowSession()
    with pytest.raises(UpstreamTimeout, match="tools/list"):
        await conn.request("tools/list", {})


@pytest.mark.asyncio
async def test_capabilities_attributeerror_falls_back_to_empty_dict(monkeypatch) -> None:
    """spawn_and_initialize returns {} when init_result.capabilities.model_dump()
    raises AttributeError. Drives the REAL spawn_and_initialize by stubbing the
    anyio-managed transport + ClientSession so we reach line 148-150 without a
    real HTTP server. init_result.capabilities lacks model_dump -> AttributeError
    -> the except branch returns {}."""
    import contextlib

    import coffer.infrastructure.mcp.http_client as mod

    # Fake streamable_http transport: an async context manager yielding
    # (read, write, get_session_id).
    @contextlib.asynccontextmanager
    async def _fake_transport(url, http_client):
        yield (object(), object(), lambda: "sid")

    class _NoModelDumpCaps:
        pass  # no model_dump() -> .model_dump() raises AttributeError

    class _InitResult:
        capabilities = _NoModelDumpCaps()

    class _FakeClientSession:
        def __init__(self, read, write, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def initialize(self):
            return _InitResult()

    monkeypatch.setattr(mod, "streamable_http_client", _fake_transport)
    monkeypatch.setattr(mod, "ClientSession", _FakeClientSession)

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )
    caps = await conn.spawn_and_initialize()
    assert caps == {}
    await conn.close()


def _patch_transport_and_session(monkeypatch, *, initialize_raises: Exception):
    """Stub the anyio transport + a ClientSession whose initialize() raises the
    given exception, so spawn_and_initialize's error-wrapping branches run
    deterministically without a real HTTP server."""
    import contextlib

    import coffer.infrastructure.mcp.http_client as mod

    @contextlib.asynccontextmanager
    async def _fake_transport(url, http_client):
        yield (object(), object(), lambda: "sid")

    class _FakeClientSession:
        def __init__(self, read, write, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def initialize(self):
            raise initialize_raises

    monkeypatch.setattr(mod, "streamable_http_client", _fake_transport)
    monkeypatch.setattr(mod, "ClientSession", _FakeClientSession)


@pytest.mark.asyncio
async def test_initialize_httpx_timeout_wraps_as_upstream_timeout(monkeypatch) -> None:
    """An httpx.TimeoutException raised during session.initialize() is wrapped as
    UpstreamTimeout (lines 131-132), and the connection is cleaned up."""
    import httpx

    _patch_transport_and_session(
        monkeypatch, initialize_raises=httpx.TimeoutException("read timed out")
    )
    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
        spawn_timeout_seconds=7,
    )
    with pytest.raises(UpstreamTimeout, match="exceeded 7s"):
        await conn.spawn_and_initialize()
    # _cleanup ran -> no session left behind.
    assert conn._session is None


@pytest.mark.asyncio
async def test_initialize_generic_error_wraps_as_upstream_unavailable(monkeypatch) -> None:
    """A generic exception during session.initialize() is wrapped as
    UpstreamUnavailable (lines 142-144) exposing only the exception TYPE name,
    never its message (CODE-039: no secret/URL leakage)."""

    class _LeakyError(RuntimeError):
        pass

    _patch_transport_and_session(
        monkeypatch,
        initialize_raises=_LeakyError("http://user:secret@host/mcp?token=abc"),
    )
    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )
    with pytest.raises(UpstreamUnavailable) as excinfo:
        await conn.spawn_and_initialize()
    msg = str(excinfo.value)
    assert "_LeakyError" in msg
    assert "secret" not in msg and "token=abc" not in msg
    assert conn._session is None


@pytest.mark.asyncio
async def test_tools_call_falls_back_when_read_timeout_kwarg_unsupported() -> None:
    """tools/call retries without read_timeout_seconds when the SDK build raises
    TypeError on that kwarg (lines 185-187), returning the fallback result."""
    fallback = object()

    class _OldSdkSession:
        def __init__(self) -> None:
            self.call_count = 0

        async def call_tool(self, name, arguments=None, read_timeout_seconds=None):
            self.call_count += 1
            if read_timeout_seconds is not None:
                raise TypeError("unexpected keyword argument 'read_timeout_seconds'")
            assert name == "ping"
            assert arguments == {"x": 1}
            return fallback

    conn = HttpUpstreamConnection(
        transport=HttpTransport(type="http", url="http://127.0.0.1:1/mcp"),
        header_overlay={},
    )
    session = _OldSdkSession()
    conn._session = session
    result = await conn.request("tools/call", {"name": "ping", "arguments": {"x": 1}})
    assert result is fallback
    assert session.call_count == 2  # first with kwarg (TypeError), then fallback
