"""Lifetime-task tests for HttpUpstreamConnection.spawn_and_initialize.

The connection's anyio-scoped transport + ClientSession live in a dedicated
task; these tests pin the two properties that design exists for:

* initialize is bounded by ``spawn_timeout_seconds`` — NOT by the httpx2
  read window (300 s) that used to govern it;
* a cancellation of the *caller* comes back out as CancelledError, not
  disguised as an upstream failure.

Both run against a raw-socket "hang" server (accepts TCP, never replies) in
a plain thread — no MCP server needed, no asyncio in the thread.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from coffer.domain.errors import UpstreamTimeout
from coffer.domain.mcp.server_config import HttpTransport
from coffer.infrastructure.mcp.http_client import HttpUpstreamConnection


@contextmanager
def _hang_server() -> Iterator[int]:
    """Accept connections and never answer them. Yields the bound port."""
    stop = threading.Event()
    ready = threading.Event()
    captured: dict[str, int] = {}

    def _serve() -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            srv.listen(8)
            srv.settimeout(0.1)
            captured["port"] = srv.getsockname()[1]
            ready.set()
            held: list[socket.socket] = []
            while not stop.is_set():
                try:
                    sock, _ = srv.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                held.append(sock)  # keep it open; say nothing
            for sock in held:
                sock.close()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    assert ready.wait(timeout=5.0), "hang server did not start"
    try:
        yield captured["port"]
    finally:
        stop.set()
        thread.join(timeout=3)


def _conn(port: int, *, spawn_timeout: int) -> HttpUpstreamConnection:
    return HttpUpstreamConnection(
        transport=HttpTransport(type="http", url=f"http://127.0.0.1:{port}/mcp"),
        header_overlay={},
        spawn_timeout_seconds=spawn_timeout,
        server_name="hanging",
    )


@pytest.mark.asyncio
async def test_initialize_hang_is_bounded_by_spawn_timeout_not_read_window() -> None:
    """A server that accepts TCP and sends nothing on initialize fails within
    spawn_timeout_seconds. Before the lifetime-task design the httpx2
    ``read=300.0`` window bounded this leg, so the call sat for five minutes
    while the docstring promised 30 s.
    """
    with _hang_server() as port:
        conn = _conn(port, spawn_timeout=1)
        started = time.monotonic()
        with pytest.raises(UpstreamTimeout, match=r"'hanging' did not finish starting within 1s"):
            await conn.spawn_and_initialize()
        elapsed = time.monotonic() - started
        # spawn_timeout + generous teardown slack; 300 s would blow this by
        # two orders of magnitude.
        assert elapsed < 1 + 3, f"spawn_and_initialize took {elapsed:.1f}s against a 1s timeout"
        assert conn._session is None
        await conn.close()  # idempotent after a failed spawn


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_as_cancelled_error() -> None:
    """Cancelling the task that awaits spawn_and_initialize surfaces as
    CancelledError — not as UpstreamUnavailable — and the connection is left
    closed and closeable. The old code re-raised every CancelledError as an
    UpstreamUnavailable, so a daemon shutdown mid-spawn looked like a dead
    upstream and the supervisor kept walking its retry ladder.
    """
    with _hang_server() as port:
        conn = _conn(port, spawn_timeout=30)
        task = asyncio.create_task(conn.spawn_and_initialize())
        await asyncio.sleep(0.2)
        assert not task.done(), "spawn should still be waiting on the hanging server"
        task.cancel()
        started = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - started < 3, "cancellation teardown was not bounded"
        assert conn._session is None
        assert conn._runner is None
        await conn.close()  # clean after cancellation
