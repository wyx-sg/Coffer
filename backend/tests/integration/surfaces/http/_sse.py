"""Read a live Server-Sent Events response straight off the ASGI app.

``httpx.ASGITransport`` and Starlette's ``TestClient`` both wait for the
response to finish before handing it back, and an event stream never finishes.
This drives the app at the ASGI level instead — the real middleware, auth
dependency and route — and exposes the body as parsed events while the stream
stays open; :meth:`SseStream.close` is the client disconnecting.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from typing import Any

from starlette.types import ASGIApp, Message


@dataclass(frozen=True)
class SseEvent:
    event: str
    data: Any
    id: str | None


class SseStream:
    def __init__(self, app: ASGIApp, path: str, headers: dict[str, str]) -> None:
        self._app = app
        self._path = path
        self._headers = [(b"host", b"localhost")] + [
            (k.lower().encode(), v.encode()) for k, v in headers.items()
        ]
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self._started: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        self._disconnect = asyncio.Event()
        self._requested = False
        self._buffer = ""
        self._task: asyncio.Task[None] | None = None
        self.body = b""

    async def open(self) -> int:
        """Send the request; return the response status once it starts."""
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": self._headers,
            "client": ("127.0.0.1", 50000),
            "server": ("localhost", 80),
        }
        self._task = asyncio.create_task(self._app(scope, self._receive, self._send))
        return await asyncio.wait_for(self._started, 5)

    async def _receive(self) -> Message:
        if not self._requested:
            self._requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self._started.set_result(message["status"])
        elif message["type"] == "http.response.body":
            self.body += message.get("body", b"")
            await self._chunks.put(message.get("body", b""))

    async def finished_body(self) -> bytes:
        """The whole body of a response that ends (an error, not a stream)."""
        assert self._task is not None
        await asyncio.wait_for(self._task, 5)
        return self.body

    async def next_event(self, timeout: float = 5.0) -> SseEvent:
        """The next event, skipping keep-alive comments."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            while "\n\n" in self._buffer:
                block, self._buffer = self._buffer.split("\n\n", 1)
                parsed = _parse(block)
                if parsed is not None:
                    return parsed
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("no event arrived")
            chunk = await asyncio.wait_for(self._chunks.get(), remaining)
            self._buffer += chunk.decode()

    async def close(self) -> None:
        self._disconnect.set()
        if self._task is not None:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self._task, 5)


def _parse(block: str) -> SseEvent | None:
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if not line or line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        fields[name] = value[1:] if value.startswith(" ") else value
    if "event" not in fields and "data" not in fields:
        return None
    return SseEvent(
        event=fields.get("event", "message"),
        data=json.loads(fields["data"]) if "data" in fields else None,
        id=fields.get("id"),
    )


__all__ = ["SseEvent", "SseStream"]
