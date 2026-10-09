"""Stop reopening an upstream's server-push stream when it closes as soon as it opens.

A streamable-HTTP MCP client opens ``GET <endpoint>`` after initialize so the
server can push notifications. The SDK reopens that stream one second after it
ends, and resets its retry budget whenever the server ended it cleanly. An
upstream that answers the GET with 200 and closes the body at once therefore
gets a new GET every second for the life of the session: Postman's hosted
server did exactly that, about ten thousand requests an hour per session, and
each one wrote two lines to the daemon log.

Server push is optional for tool calls: requests and their responses travel on
POST. So after a few streams in a row that each ended within
:data:`QUICK_CLOSE_SECONDS`, the guard refuses further GETs for that connection
with :class:`PushStreamDisabled`; the SDK counts the refusal as a failed
reconnect and stops after its own retry budget. A stream that stays open
longer resets the count, so an upstream that pushes normally is never cut off.

The guard sits in :meth:`httpx2.AsyncClient.send` rather than in a transport,
because a proxy taken from the environment is mounted as its own transport and
would bypass a wrapped one.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx2

log = logging.getLogger(__name__)

#: A push stream that ends sooner than this after it opened counts as closed at once.
QUICK_CLOSE_SECONDS = 5.0
#: How many such streams in a row before the connection stops opening new ones.
GIVE_UP_AFTER = 3


class PushStreamDisabled(httpx2.TransportError):
    """The upstream keeps closing its push stream at once; it is not reopened."""


def is_push_stream_request(request: httpx2.Request) -> bool:
    """Whether ``request`` opens the server-push stream: a GET asking for an event stream."""
    return request.method == "GET" and "text/event-stream" in request.headers.get("accept", "")


class PushStreamGuard:
    """Counts push streams that closed at once and decides when to stop reopening them."""

    def __init__(
        self,
        server_name: str,
        *,
        quick_close_seconds: float = QUICK_CLOSE_SECONDS,
        give_up_after: int = GIVE_UP_AFTER,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._server_name = server_name
        self._quick_close_seconds = quick_close_seconds
        self._give_up_after = give_up_after
        self._clock = clock
        self._quick_closes = 0
        self.disabled = False

    def opened(self) -> float:
        """Note a stream that just opened; returns the time to hand back to :meth:`closed`."""
        return self._clock()

    def closed(self, opened_at: float) -> None:
        """Note that the stream opened at ``opened_at`` has ended."""
        if self._clock() - opened_at >= self._quick_close_seconds:
            self._quick_closes = 0
            return
        self._quick_closes += 1
        if self._quick_closes >= self._give_up_after and not self.disabled:
            self.disabled = True
            log.info(
                "mcp.push_stream.disabled",
                extra={"server": self._server_name, "quick_closes": self._quick_closes},
            )


class _ClosingStream(httpx2.AsyncByteStream):
    """Passes a response body through and reports once when it is closed."""

    def __init__(self, inner: Any, on_close: Callable[[], None]) -> None:
        self._inner = inner
        self._on_close: Callable[[], None] | None = on_close

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._inner:
            yield chunk

    async def aclose(self) -> None:
        try:
            await self._inner.aclose()
        finally:
            on_close, self._on_close = self._on_close, None
            if on_close is not None:
                on_close()


class GuardedAsyncClient(httpx2.AsyncClient):
    """An ``httpx2.AsyncClient`` whose push-stream GETs go through a :class:`PushStreamGuard`."""

    def __init__(self, *, guard: PushStreamGuard, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.push_stream_guard = guard

    async def send(self, request: httpx2.Request, **kwargs: Any) -> httpx2.Response:
        if not is_push_stream_request(request):
            return await super().send(request, **kwargs)
        guard = self.push_stream_guard
        if guard.disabled:
            raise PushStreamDisabled(
                "the upstream closes its push stream as soon as it opens; not reopening it",
                request=request,
            )
        response = await super().send(request, **kwargs)
        if response.is_success:
            opened_at = guard.opened()
            response.stream = _ClosingStream(response.stream, lambda: guard.closed(opened_at))
        return response


__all__ = [
    "GIVE_UP_AFTER",
    "QUICK_CLOSE_SECONDS",
    "GuardedAsyncClient",
    "PushStreamDisabled",
    "PushStreamGuard",
    "is_push_stream_request",
]
