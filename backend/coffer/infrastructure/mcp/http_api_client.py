"""The HTTP API "upstream": custom tools the gateway runs as HTTP requests.

Spec mcp-gateway "Serve an HTTP API as a group of custom tools" and "Make a
custom tool's request in the gateway"; design add-http-custom-tools §1, §3, §4.

Same contract as the stdio and HTTP-MCP connections (``spawn_and_initialize``,
``request``, the callback setters, ``close``), so the supervisor, discovery,
the per-call gates and the invocation log treat a group like any other server.
There is no process and no MCP peer: ``tools/list`` is answered from the
group's config and ``tools/call`` makes the tool's HTTP request here.

The request is made with no redirect followed (a 3xx is returned as a result,
so the auth header is never carried somewhere nobody configured), the group's
timeout, and at most 1 MiB of the response read. The secret arrives in
``header_overlay`` — materialised by the supervisor through the guarded
resolver for this group's base URL — and its value is masked out of every
result before it leaves this module.

The base URL is an endpoint the user configured as their own, so these calls
are exempt from the SSRF guard (Principles → Network defaults).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

import httpx
import mcp.types as mcp_types
from mcp import MCPError

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_render import RenderedRequest, RenderError, render_request

#: The most of a response body a tool returns (spec: "read at most 1 MiB").
MAX_RESPONSE_BYTES = 1024 * 1024
MASK = "***"

NotificationCallback = Callable[[Any], Awaitable[None]]


def tool_annotations(tool: HttpApiTool) -> mcp_types.ToolAnnotations:
    """Spec mcp-gateway "Annotate every tool with whether it changes data"."""
    if tool.effective_changes_data:
        return mcp_types.ToolAnnotations(read_only_hint=False, destructive_hint=True)
    return mcp_types.ToolAnnotations(read_only_hint=True)


def list_tools_result(transport: HttpApiTransport) -> mcp_types.ListToolsResult:
    return mcp_types.ListToolsResult(
        tools=[
            mcp_types.Tool(
                name=t.name,
                description=t.description or t.request_label,
                input_schema=t.input_schema,
                annotations=tool_annotations(t),
            )
            for t in transport.tools
        ]
    )


def _text_result(text: str, *, is_error: bool) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)], is_error=is_error
    )


class HttpCallOutcome:
    """What one request returned, before it is shaped into a tool result."""

    __slots__ = ("body", "content_type", "duration_ms", "location", "status", "truncated", "url")

    def __init__(
        self,
        *,
        url: str,
        status: int,
        body: str,
        truncated: bool,
        duration_ms: int,
        content_type: str | None,
        location: str | None,
    ) -> None:
        self.url = url
        self.status = status
        self.body = body
        self.truncated = truncated
        self.duration_ms = duration_ms
        self.content_type = content_type
        self.location = location

    @property
    def is_error(self) -> bool:
        return self.status >= 400

    def status_line(self) -> str:
        try:
            reason = HTTPStatus(self.status).phrase
        except ValueError:
            reason = ""
        return f"HTTP {self.status} {reason}".rstrip()

    def as_text(self) -> str:
        parts = [self.status_line()]
        if self.location is not None:
            parts.append(f"Location: {self.location} (not followed)")
        text = "\n".join(parts)
        if self.body:
            text += "\n\n" + self.body
        if self.truncated:
            text += f"\n\n[response cut at {MAX_RESPONSE_BYTES} bytes]"
        return text


def mask_secrets(text: str, secrets: list[str]) -> str:
    for value in secrets:
        if value:
            text = text.replace(value, MASK)
    return text


def build_request(
    transport: HttpApiTransport,
    tool: HttpApiTool,
    arguments: dict[str, Any] | None,
    header_overlay: dict[str, str],
) -> RenderedRequest:
    """The request for ``tool``, the auth header added last (so no tool
    header can replace it)."""
    rendered = render_request(
        base_url=str(transport.base_url),
        method=tool.method,
        path=tool.path,
        group_headers=transport.headers,
        tool_headers=tool.headers,
        body_template=tool.body_template,
        input_schema=tool.input_schema,
        arguments=arguments,
    )
    if transport.auth_header and transport.auth_header in header_overlay:
        # Header names compare case-insensitively: drop any spelling a tool gave.
        for name in [n for n in rendered.headers if n.lower() == transport.auth_header.lower()]:
            del rendered.headers[name]
        rendered.headers[transport.auth_header] = (
            transport.auth_prefix + header_overlay[transport.auth_header]
        )
    return rendered


async def send_request(
    request: RenderedRequest,
    *,
    timeout_seconds: float,
    secrets: list[str],
    client_factory: Callable[[], httpx.AsyncClient] | None = None,
) -> HttpCallOutcome:
    """Send one request. Raises ``UpstreamTimeout``; returns every answer.

    A connection failure is reported as an outcome with status 0 rather than
    raised: the "upstream" is this module, and it is healthy.
    """
    started = time.monotonic()
    client = (
        client_factory()
        if client_factory is not None
        else httpx.AsyncClient(follow_redirects=False, timeout=timeout_seconds)
    )
    try:
        async with client.stream(
            request.method, request.url, headers=request.headers, content=request.body
        ) as response:
            chunks: list[bytes] = []
            size = 0
            truncated = False
            async for chunk in response.aiter_bytes():
                room = MAX_RESPONSE_BYTES - size
                if len(chunk) > room:
                    chunks.append(chunk[:room])
                    truncated = True
                    break
                chunks.append(chunk)
                size += len(chunk)
            raw = b"".join(chunks)
            body = raw.decode(response.encoding or "utf-8", errors="replace")
            location = response.headers.get("location") if response.is_redirect else None
            return HttpCallOutcome(
                url=mask_secrets(request.url, secrets),
                status=response.status_code,
                body=mask_secrets(body, secrets),
                truncated=truncated,
                duration_ms=int((time.monotonic() - started) * 1000),
                content_type=response.headers.get("content-type"),
                location=mask_secrets(location, secrets) if location else None,
            )
    except httpx.TimeoutException as e:
        raise UpstreamTimeout(f"request timed out after {timeout_seconds:g}s") from e
    except httpx.HTTPError as e:
        host = httpx.URL(request.url).host
        return HttpCallOutcome(
            url=mask_secrets(request.url, secrets),
            status=0,
            body=f"could not reach {host}: {type(e).__name__}",
            truncated=False,
            duration_ms=int((time.monotonic() - started) * 1000),
            content_type=None,
            location=None,
        )
    finally:
        await client.aclose()


class HttpApiUpstreamConnection:
    """One custom-tool group, served in-process."""

    def __init__(
        self,
        *,
        transport: HttpApiTransport,
        header_overlay: dict[str, str],
        server_name: str,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._transport = transport
        self._overlay = dict(header_overlay)
        self._server_name = server_name
        self._client_factory = client_factory
        self._closed = False

    def on_notification(self, cb: NotificationCallback) -> None:
        """Nothing to forward: a group's list changes only when its config does,
        and a config change evicts this connection."""

    def on_sampling_request(self, cb: Any) -> None:
        """A group never asks the client to sample."""

    def on_roots_request(self, cb: Any) -> None:
        """A group never asks the client for roots."""

    async def spawn_and_initialize(self) -> dict[str, Any]:
        return {"tools": {"listChanged": False}}

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        if self._closed:
            raise UpstreamUnavailable(f"{self._server_name!r} connection is closed")
        if method == "tools/list":
            return list_tools_result(self._transport)
        if method == "tools/call":
            return await self._call(str(params.get("name", "")), params.get("arguments"))
        if method in ("resources/list", "prompts/list", "resources/read", "prompts/get"):
            raise MCPError(mcp_types.METHOD_NOT_FOUND, f"{method} is not offered by a tool group")
        raise UpstreamUnavailable(f"method not supported by gateway: {method!r}")

    async def _call(self, name: str, arguments: Any) -> mcp_types.CallToolResult:
        tool = self._transport.tool(name)
        if tool is None:
            return _text_result(f"no tool {name!r} in this group", is_error=True)
        args = arguments if isinstance(arguments, dict) else {}
        secrets = list(self._overlay.values())
        try:
            request = build_request(self._transport, tool, args, self._overlay)
        except RenderError as e:
            return _text_result(mask_secrets(str(e), secrets), is_error=True)
        outcome = await send_request(
            request,
            timeout_seconds=self._transport.timeout_seconds,
            secrets=secrets,
            client_factory=self._client_factory,
        )
        return _text_result(outcome.as_text(), is_error=outcome.is_error or outcome.status == 0)

    async def close(self) -> None:
        self._closed = True
        self._overlay.clear()


__all__ = [
    "MAX_RESPONSE_BYTES",
    "HttpApiUpstreamConnection",
    "HttpCallOutcome",
    "build_request",
    "list_tools_result",
    "mask_secrets",
    "send_request",
    "tool_annotations",
]
