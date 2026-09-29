"""Real loopback servers for the model-proxy integration tests.

Both the proxy app and the fake upstreams run under uvicorn on random
127.0.0.1 ports, each in its own thread and event loop — so requests cross a
real socket, streaming is real (``httpx.ASGITransport`` buffers whole
responses), the ``Host`` check sees a real listener port, and a client that
hangs up produces a real ``http.disconnect``.

A :class:`FakeUpstream` records every request it gets (path, query, raw
headers, body bytes) and answers with whatever script the test set.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from starlette.types import ASGIApp, Receive, Scope, Send


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class ServerThread:
    """``app`` served by uvicorn on a random loopback port in a thread."""

    def __init__(self, app: ASGIApp, *, lifespan: str = "on") -> None:
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self.port = int(self._sock.getsockname()[1])
        config = uvicorn.Config(
            app,
            fd=self._sock.fileno(),
            lifespan=lifespan,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=1,
        )
        self.server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> ServerThread:
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("server did not start")
            time.sleep(0.01)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self._thread.join(10)
        self._sock.close()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@dataclass
class Recorded:
    method: str
    path: str
    query: bytes
    headers: list[tuple[bytes, bytes]]
    body: bytes
    disconnected: threading.Event = field(default_factory=threading.Event)

    def header(self, name: str) -> str | None:
        for k, v in self.headers:
            if k.decode().lower() == name:
                return v.decode()
        return None

    def all(self, name: str) -> list[str]:
        return [v.decode() for k, v in self.headers if k.decode().lower() == name]


Script = Callable[[Recorded, Send], Awaitable[None]]


class FakeUpstream:
    """An ASGI app that records requests and plays ``script`` for each one."""

    def __init__(self) -> None:
        self.requests: list[Recorded] = []
        self.script: Script = json_reply(200, {"ok": True})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        rec = Recorded(
            scope["method"], scope["path"], scope["query_string"], list(scope["headers"]), body
        )
        self.requests.append(rec)

        async def _watch() -> None:
            while (await receive())["type"] != "http.disconnect":
                pass
            rec.disconnected.set()

        watcher = asyncio.create_task(_watch())
        try:
            await self.script(rec, send)
        except OSError:
            rec.disconnected.set()
        finally:
            await asyncio.sleep(0)
            if not rec.disconnected.is_set():
                watcher.cancel()


def json_reply(status: int, payload: Any, headers: dict[str, str] | None = None) -> Script:
    async def _script(rec: Recorded, send: Send) -> None:
        raw = [(b"content-type", b"application/json")]
        raw += [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
        await send({"type": "http.response.start", "status": status, "headers": raw})
        await send({"type": "http.response.body", "body": json.dumps(payload).encode()})

    return _script


def sse_reply(
    chunks: list[bytes],
    *,
    headers: dict[str, str] | None = None,
    delay: float = 0.0,
    hang_after: bool = False,
) -> Script:
    """Stream ``chunks`` (with ``delay`` between them); ``hang_after`` keeps the
    stream open afterwards until the proxy hangs up."""

    async def _script(rec: Recorded, send: Send) -> None:
        raw = [(b"content-type", b"text/event-stream")]
        raw += [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
        await send({"type": "http.response.start", "status": 200, "headers": raw})
        for chunk in chunks:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
            if delay:
                await asyncio.sleep(delay)
        if hang_after:
            for _ in range(600):
                if rec.disconnected.is_set():
                    return
                await asyncio.sleep(0.05)
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    return _script


def sse(name: str, data: dict[str, Any]) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()
