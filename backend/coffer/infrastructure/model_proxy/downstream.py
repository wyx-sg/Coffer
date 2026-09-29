"""The agent's side of one relayed request: sending, and noticing it left.

The relay writes the upstream's bytes to the agent as they arrive, and it must
stop — closing the upstream stream, so a cancelled Claude Code turn stops
billing — the moment the agent goes away. ASGI reports that as an
``http.disconnect`` message on ``receive``; once the request body has been
read, a watcher task is the only reader of ``receive``, and it both sets
:attr:`Downstream.gone` and drops a :data:`GONE` marker into whichever
upstream queue the relay is currently waiting on, so the wait wakes at once.
A ``send`` that raises (the socket is already closed) counts as the same thing.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from starlette.types import Receive, Send

#: Queue markers shared with :mod:`.relay`.
END: Any = object()
GONE: Any = object()
TIMEOUT: Any = object()


class Broken:
    """The upstream stream failed after its headers (read error, idle timeout)."""

    def __init__(self, error: BaseException) -> None:
        self.error = error


class Downstream:
    def __init__(self, receive: Receive, send: Send) -> None:
        self._receive = receive
        self._send = send
        self.gone = asyncio.Event()
        self.queue: asyncio.Queue[Any] | None = None
        self.started = False

    async def watch(self) -> None:
        """Wait for the agent to disconnect; run as a task for the request's life."""
        while True:
            message = await self._receive()
            if message["type"] == "http.disconnect":
                self._mark_gone()
                return

    def _mark_gone(self) -> None:
        self.gone.set()
        queue = self.queue
        if queue is not None:
            queue.put_nowait(GONE)

    async def start(self, status: int, headers: list[tuple[bytes, bytes]]) -> bool:
        try:
            await self._send({"type": "http.response.start", "status": status, "headers": headers})
        except Exception:
            self._mark_gone()
            return False
        self.started = True
        return True

    async def body(self, chunk: bytes, *, more: bool = True) -> bool:
        if self.gone.is_set():
            return False
        try:
            await self._send({"type": "http.response.body", "body": chunk, "more_body": more})
        except Exception:
            self._mark_gone()
            return False
        return True

    async def respond(self, status: int, headers: list[tuple[bytes, bytes]], body: bytes) -> None:
        """A whole response at once (a held upstream error, a synthetic refusal)."""
        if await self.start(status, headers):
            await self.body(body, more=False)


async def next_item(queue: asyncio.Queue[Any], timeout: float | None) -> Any:
    """The next queued item, or :data:`TIMEOUT` once ``timeout`` seconds pass."""
    if timeout is not None and timeout <= 0:
        return queue.get_nowait() if not queue.empty() else TIMEOUT
    try:
        return await asyncio.wait_for(queue.get(), timeout)
    except TimeoutError:
        return TIMEOUT


async def cancel_quietly(task: asyncio.Future[Any] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(BaseException):
        await task


__all__ = ["END", "GONE", "TIMEOUT", "Broken", "Downstream", "cancel_quietly", "next_item"]
