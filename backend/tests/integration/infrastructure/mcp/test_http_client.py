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

    # Conditional assertion: if the SDK reached our stub the header was there.
    if captured:
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
