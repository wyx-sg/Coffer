"""HTTP/SSE upstream connection — async wrapper around an mcp ClientSession.

Same external contract as StdioUpstreamConnection (spawn_and_initialize,
request, on_notification, close), but the underlying transport is the
official mcp SDK's `streamable_http_client` against a remote HTTP MCP
endpoint.

Headers (including materialised credentials) are injected via an
httpx.AsyncClient that we create and manage here; this is the SDK-blessed
approach as of mcp >=1.8 (the legacy `streamablehttp_client` helper that
accepted headers directly is deprecated in that version).

IMPORTANT: asyncio.wait_for must NOT wrap any code that runs inside anyio
task groups.  The mcp SDK's streamable_http_client (and therefore
ClientSession.initialize) runs entirely inside an anyio task group; wrapping
those calls with asyncio.wait_for causes anyio to raise a RuntimeError when
the coroutine is cancelled from outside its owning task group.  Instead we
configure httpx.Timeout for spawn-phase timeouts and let anyio propagate
genuine transport errors up to us as exceptions.

The 'spawn' word is preserved for symmetry with stdio even though no
subprocess is spawned — it's the upstream-side connection lifecycle.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack, suppress
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.session import ListRootsFnT, SamplingFnT
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.types import ServerNotification

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import HttpTransport

NotificationCallback = Callable[[Any], Awaitable[None]]


class HttpUpstreamConnection:
    """One open HTTP+SSE session with one upstream MCP server."""

    def __init__(
        self,
        transport: HttpTransport,
        header_overlay: dict[str, str],
        spawn_timeout_seconds: int = 30,
        request_timeout_seconds: int = 120,
    ) -> None:
        self._transport = transport
        self._header_overlay = header_overlay
        self._spawn_timeout = spawn_timeout_seconds
        self._request_timeout = request_timeout_seconds

        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
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
        merged and injected into every request via the httpx.AsyncClient.

        Timeout enforcement: httpx.Timeout(spawn_timeout_seconds) covers the
        underlying HTTP connect + read for the initialize RPC.  We do not use
        asyncio.wait_for around anyio-managed contexts — that would violate
        anyio's cancel-scope-per-task invariant and raise RuntimeError.
        """
        # Combine static headers from config with materialised credentials.
        merged_headers: dict[str, str] = {**self._transport.headers, **self._header_overlay}

        # httpx.Timeout: connect + individual requests use spawn_timeout_seconds.
        # read=300 is a generous SSE-stream read window for post-init use.
        http_client = create_mcp_http_client(
            headers=merged_headers or None,
            timeout=httpx.Timeout(float(self._spawn_timeout), read=300.0),
        )

        self._exit_stack = AsyncExitStack()
        try:
            # Enter the anyio-managed transport — no asyncio.wait_for here.
            read, write, _get_session_id = await self._exit_stack.enter_async_context(
                streamable_http_client(
                    str(self._transport.url),
                    http_client=http_client,
                )
            )
            session = await self._exit_stack.enter_async_context(
                ClientSession(
                    read,
                    write,
                    message_handler=self._message_handler,
                    sampling_callback=self._sampling_callback,
                    list_roots_callback=self._list_roots_callback,
                )
            )
            # session.initialize() sends the initialize request over HTTP; the
            # httpx timeout (spawn_timeout_seconds) bounds how long this takes.
            # We do NOT wrap this in asyncio.wait_for — doing so would cancel
            # from outside anyio's task group and trigger its RuntimeError.
            init_result = await session.initialize()
        except httpx.TimeoutException as exc:
            await self._cleanup()
            raise UpstreamTimeout(f"upstream init exceeded {self._spawn_timeout}s") from exc
        except asyncio.CancelledError as exc:
            # anyio propagates connection failures (e.g. ConnectError in its
            # background task group) as a CancelledError to the awaiting
            # coroutine.  Wrap it so callers get a domain error.
            await self._cleanup()
            # CODE-039: httpx/transport exceptions can embed the request URL
            # (which may carry a query-string secret) or reflected headers.
            # Surface only the exception type; chain the original via ``from``.
            raise UpstreamUnavailable(f"upstream init cancelled: {type(exc).__name__}") from exc
        except Exception as exc:
            await self._cleanup()
            raise UpstreamUnavailable(f"upstream init failed: {type(exc).__name__}") from exc

        self._session = session
        try:
            capabilities: dict[str, Any] = init_result.capabilities.model_dump()
        except AttributeError:
            capabilities = {}
        return capabilities

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        """Forward a single MCP request, with timeout.  Returns the SDK result object."""
        if self._session is None:
            raise UpstreamUnavailable("upstream not initialized")
        # The httpx client was created with a read timeout of 300 s; for
        # per-request control we rely on the caller to set request_timeout_seconds
        # appropriately.  asyncio.wait_for is safe here because we are outside
        # any anyio task group at this call site.
        try:
            return await asyncio.wait_for(
                self._dispatch_method(method, params),
                timeout=float(self._request_timeout),
            )
        except TimeoutError as exc:
            raise UpstreamTimeout(f"upstream {method} exceeded {self._request_timeout}s") from exc

    async def _dispatch_method(self, method: str, params: dict[str, Any]) -> Any:
        assert self._session is not None
        if method == "tools/list":
            return await self._session.list_tools()
        if method == "tools/call":
            # T-060: pass read_timeout_seconds so the SDK resets the idle timer
            # on every notifications/progress event, preventing premature timeout
            # of long-running tools that stream progress.
            from datetime import timedelta

            try:
                return await self._session.call_tool(
                    params["name"],
                    arguments=params.get("arguments"),
                    read_timeout_seconds=timedelta(seconds=float(self._request_timeout)),
                )
            except TypeError:
                # Older SDK build that doesn't accept read_timeout_seconds
                return await self._session.call_tool(
                    params["name"], arguments=params.get("arguments")
                )
        if method == "resources/list":
            return await self._session.list_resources()
        if method == "resources/read":
            return await self._session.read_resource(params["uri"])
        if method == "prompts/list":
            return await self._session.list_prompts()
        if method == "prompts/get":
            return await self._session.get_prompt(params["name"], arguments=params.get("arguments"))
        raise UpstreamUnavailable(f"method not supported by gateway: {method!r}")

    async def close(self) -> None:
        """Close the upstream connection gracefully."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        if self._exit_stack is not None:
            with suppress(TimeoutError, asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._exit_stack.aclose(), timeout=5.0)
            self._exit_stack = None
        self._session = None
