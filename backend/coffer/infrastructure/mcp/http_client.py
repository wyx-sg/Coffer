"""HTTP/SSE upstream connection — async wrapper around an mcp ClientSession.

Same external contract as StdioUpstreamConnection (spawn_and_initialize,
request, on_notification, close), but the underlying transport is the
official mcp SDK's `streamable_http_client` against a remote HTTP MCP
endpoint.

Headers (including materialised credentials) are injected via an
httpx2.AsyncClient that we create and manage here; this is the SDK-blessed
approach — the legacy `streamablehttp_client` helper that accepted headers
directly was removed in mcp 2.0. httpx2 (not httpx) is the client library the
mcp SDK builds on as of 2.0, so the timeout and exception types here come from
it.

IMPORTANT: asyncio.wait_for must NOT wrap any code that runs inside anyio
task groups.  The mcp SDK's streamable_http_client (and therefore
ClientSession.initialize) runs entirely inside anyio task groups whose
cancel scopes must be entered and exited by the SAME task, in LIFO order;
wrapping those awaits in asyncio.wait_for / asyncio.timeout and closing the
contexts later from another scope makes anyio raise RuntimeError.

So the connection's anyio-scoped objects (transport + ClientSession) live in
a dedicated *lifetime task*: it enters them, runs ``initialize``, publishes
the outcome through a future, then parks on a close event and tears the
contexts down in that same task.  ``spawn_and_initialize`` only waits on the
future — bounded by ``spawn_timeout_seconds`` — and ``close`` only pokes the
event; neither ever touches an anyio cancel scope from the wrong task.
Requests from other tasks keep using the session directly: ``send_request``
awaits memory streams, which anyio permits across tasks.

The 'spawn' word is preserved for symmetry with stdio even though no
subprocess is spawned — it's the upstream-side connection lifecycle.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, suppress
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.session import ListRootsFnT, SamplingFnT
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.types import ServerNotification

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import HttpTransport
from coffer.infrastructure.mcp.dispatch import dispatch_method

NotificationCallback = Callable[[Any], Awaitable[None]]

# How long close() waits for the lifetime task to unwind its anyio contexts
# before cancelling it outright (and then how long it waits for that).
_TEARDOWN_SECONDS = 5.0

# Read window for the httpx2 client. This is the SSE *streaming* budget for
# post-init use (a long tools/call streaming progress); it deliberately does
# NOT bound initialize — spawn_and_initialize enforces spawn_timeout_seconds
# itself, from outside the anyio scopes.
_STREAM_READ_SECONDS = 300.0


def _leaf_exception(exc: BaseException) -> BaseException:
    """Unwrap single-member exception groups so the real transport error is named.

    anyio surfaces a crashed transport task as a (possibly nested)
    ExceptionGroup on scope exit; a one-leaf group is the one exception it
    carries.
    """
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


class HttpUpstreamConnection:
    """One open HTTP+SSE session with one upstream MCP server."""

    def __init__(
        self,
        transport: HttpTransport,
        header_overlay: dict[str, str],
        spawn_timeout_seconds: int = 30,
        request_timeout_seconds: int = 120,
        server_name: str = "upstream",
    ) -> None:
        self._transport = transport
        self._header_overlay = header_overlay
        self._spawn_timeout = spawn_timeout_seconds
        self._request_timeout = request_timeout_seconds
        # Named so a timeout can say WHICH server stalled. An agent waiting out
        # a 120s request timeout with no attribution cannot tell a slow upstream
        # from a broken Coffer.
        self._server_name = server_name

        self._session: ClientSession | None = None
        # The lifetime task and the two handles spawn/close talk to it with.
        self._runner: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[Any] | None = None
        self._close_event: asyncio.Event | None = None
        self._notification_callback: NotificationCallback | None = None
        # Server-initiated request callbacks (T-061/T-062)
        self._sampling_callback: SamplingFnT | None = None
        self._list_roots_callback: ListRootsFnT | None = None

    def on_notification(self, cb: NotificationCallback) -> None:
        """Register a callback that receives every upstream-initiated notification."""
        self._notification_callback = cb

    def on_sampling_request(self, cb: SamplingFnT) -> None:
        """Register a callback that handles sampling/createMessage requests from the upstream."""
        self._sampling_callback = cb

    def on_roots_request(self, cb: ListRootsFnT) -> None:
        """Register a callback that handles roots/list requests from the upstream."""
        self._list_roots_callback = cb

    async def _message_handler(self, message: Any) -> None:
        """Forward ServerNotifications to the registered callback."""
        if isinstance(message, ServerNotification) and self._notification_callback is not None:
            with suppress(Exception):
                await self._notification_callback(message)

    async def spawn_and_initialize(self) -> dict[str, Any]:
        """Open the HTTP/SSE connection and complete MCP initialize.

        Returns the server's capabilities as a plain dict.
        Headers from the transport config and the credential overlay are
        merged and injected into every request via the httpx2.AsyncClient.

        Timeout enforcement: the whole connect + initialize phase is bounded
        by ``spawn_timeout_seconds``, measured here while waiting on the
        lifetime task's ready-future — so a server that accepts the TCP
        connection and then says nothing fails in ``spawn_timeout_seconds``,
        not after the httpx2 read window.  On timeout the lifetime task is
        cancelled (it unwinds its own anyio scopes) and UpstreamTimeout is
        raised.  If the *caller* is cancelled the connection is torn down the
        same way and the CancelledError is re-raised untouched, so a daemon
        shutdown is never mistaken for an upstream failure.
        """
        # Combine static headers from config with materialised credentials.
        merged_headers: dict[str, str] = {**self._transport.headers, **self._header_overlay}

        # httpx2.Timeout: connect/write/pool use spawn_timeout_seconds; the
        # read window is the post-init SSE streaming budget (see module note).
        http_client = create_mcp_http_client(
            headers=merged_headers or None,
            timeout=httpx2.Timeout(float(self._spawn_timeout), read=_STREAM_READ_SECONDS),
        )

        loop = asyncio.get_running_loop()
        ready: asyncio.Future[Any] = loop.create_future()
        close_event = asyncio.Event()
        self._ready = ready
        self._close_event = close_event
        self._runner = asyncio.create_task(
            self._run_lifetime(http_client, ready, close_event),
            name=f"coffer-mcp-http-upstream:{self._server_name}",
        )

        try:
            # asyncio.wait (not wait_for) — it neither cancels the future nor
            # re-raises its exception, so the outcome is classified below.
            done, _pending = await asyncio.wait({ready}, timeout=float(self._spawn_timeout))
        except asyncio.CancelledError:
            await self._cleanup()
            raise
        if not done:
            await self._cleanup()
            raise UpstreamTimeout(
                f"MCP server {self._server_name!r} did not finish starting within "
                f"{self._spawn_timeout}s (its spawn timeout)"
            )
        if ready.cancelled():
            await self._cleanup()
            raise UpstreamUnavailable("upstream init cancelled: CancelledError")
        exc = ready.exception()
        if exc is not None:
            await self._cleanup()
            raise self._init_error(exc) from exc

        init_result = ready.result()
        try:
            capabilities: dict[str, Any] = init_result.capabilities.model_dump(by_alias=True)
        except AttributeError:
            capabilities = {}
        return capabilities

    def _init_error(self, exc: BaseException) -> UpstreamTimeout | UpstreamUnavailable:
        """Map a lifetime-task failure onto a domain error.

        httpx2/transport exceptions can embed the request URL (which
        may carry a query-string secret) or reflected headers.  Surface only
        the exception type; callers chain the original via ``from``.
        """
        leaf = _leaf_exception(exc)
        if isinstance(leaf, httpx2.TimeoutException):
            return UpstreamTimeout(
                f"MCP server {self._server_name!r} did not finish starting within "
                f"{self._spawn_timeout}s (its spawn timeout)"
            )
        if isinstance(leaf, asyncio.CancelledError):
            # anyio delivers a crashed transport task to the awaiting coroutine
            # as a CancelledError; when scope exit surfaced nothing better,
            # this is all we know.
            return UpstreamUnavailable(f"upstream init cancelled: {type(leaf).__name__}")
        return UpstreamUnavailable(f"upstream init failed: {type(leaf).__name__}")

    async def _run_lifetime(
        self,
        http_client: httpx2.AsyncClient,
        ready: asyncio.Future[Any],
        close_event: asyncio.Event,
    ) -> None:
        """Own the transport + ClientSession for the connection's whole life.

        Runs as its own task so every anyio cancel scope the SDK opens is
        entered and exited by this task, in order.  Publishes the initialize
        result (or the failure) on ``ready``, then parks until ``close_event``
        is set — or until anyio cancels us because the transport died — and
        finally unwinds the contexts here.
        """
        exit_stack = AsyncExitStack()
        session: ClientSession | None = None
        init_error: BaseException | None = None
        init_result: Any = None
        try:
            try:
                read, write = await exit_stack.enter_async_context(
                    streamable_http_client(
                        str(self._transport.url),
                        http_client=http_client,
                    )
                )
                session = await exit_stack.enter_async_context(
                    ClientSession(
                        read,
                        write,
                        message_handler=self._message_handler,
                        sampling_callback=self._sampling_callback,
                        list_roots_callback=self._list_roots_callback,
                    )
                )
                init_result = await session.initialize()
            except (Exception, asyncio.CancelledError) as exc:
                init_error = exc

            if init_error is None:
                self._session = session
                if not ready.done():
                    ready.set_result(init_result)
                # Parked here for the life of the connection. A CancelledError
                # is either close() giving up on a polite teardown, or anyio
                # reporting that the transport's own tasks crashed.
                with suppress(asyncio.CancelledError):
                    await close_event.wait()
        finally:
            close_error: BaseException | None = None
            try:
                await exit_stack.aclose()
            except (Exception, asyncio.CancelledError, BaseExceptionGroup) as exc:
                close_error = exc
            if self._session is session:
                self._session = None
            if not ready.done():
                # A crashed transport reaches initialize() as a bare
                # CancelledError; the cause only shows on scope exit, so
                # prefer that when there is one.
                publish = init_error
                if isinstance(publish, asyncio.CancelledError) and close_error is not None:
                    publish = close_error
                if publish is None:
                    ready.cancel()
                else:
                    ready.set_exception(publish)

    async def request(
        self,
        method: str,
        params: dict[str, Any],
        progress_callback: Any | None = None,
    ) -> Any:
        """Forward a single MCP request, with timeout.  Returns the SDK result object."""
        if self._session is None:
            raise UpstreamUnavailable("upstream not initialized")
        # The httpx2 client was created with a read timeout of 300 s; for
        # per-request control we rely on the caller to set request_timeout_seconds
        # appropriately. Despite the module-header rule, asyncio.wait_for is
        # safe at THIS call site: we await session.send_request from
        # outside the SDK's anyio task group, so cancellation lands on our
        # coroutine, not inside the group (no cross-task cancel-scope error).
        # The connection deliberately stays cached after an UpstreamTimeout
        # (the gateway does not evict on timeout): the SDK matches responses
        # by request id, so a late reply to the abandoned id is discarded and
        # cannot corrupt the next request on this session.
        try:
            return await asyncio.wait_for(
                self._dispatch_method(method, params, progress_callback=progress_callback),
                timeout=float(self._request_timeout),
            )
        except TimeoutError as exc:
            raise UpstreamTimeout(
                f"MCP server {self._server_name!r} did not answer {method} within "
                f"{self._request_timeout}s (its request timeout)"
            ) from exc

    async def _dispatch_method(
        self,
        method: str,
        params: dict[str, Any],
        progress_callback: Any | None = None,
    ) -> Any:
        assert self._session is not None
        return await dispatch_method(
            self._session,
            method,
            params,
            request_timeout_seconds=float(self._request_timeout),
            progress_callback=progress_callback,
        )

    async def close(self) -> None:
        """Close the upstream connection gracefully."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Stop the lifetime task (bounded) and forget the session.

        Idempotent. The task unwinds its own anyio contexts; we only ask it
        to (close event), wait up to _TEARDOWN_SECONDS, then cancel it and
        wait once more. A connection still inside initialize is cancelled
        straight away — there is nothing polite to wait for.
        """
        runner, self._runner = self._runner, None
        ready, self._ready = self._ready, None
        close_event, self._close_event = self._close_event, None
        self._session = None
        if runner is None:
            return
        if close_event is not None:
            close_event.set()
        try:
            if ready is not None and not ready.done():
                runner.cancel()
            # asyncio.wait (not wait_for) never re-raises the task's outcome
            # — a cancelled runner must not read as OUR cancellation.
            await asyncio.wait({runner}, timeout=_TEARDOWN_SECONDS)
            if not runner.done():
                runner.cancel()
                await asyncio.wait({runner}, timeout=_TEARDOWN_SECONDS)
        except asyncio.CancelledError:
            runner.cancel()  # best effort: let it unwind in the background
            raise
        finally:
            # Retrieve outcomes we will never look at again so asyncio does
            # not log "exception was never retrieved" at GC time.
            if runner.done() and not runner.cancelled():
                runner.exception()
            if ready is not None and ready.done() and not ready.cancelled():
                ready.exception()
