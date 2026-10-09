"""The HTTP API "upstream": custom tools the gateway runs as HTTP requests.

Spec mcp-gateway "Serve an HTTP API as a group of custom tools" and "Make a
custom tool's request in the gateway"; design add-http-custom-tools §1, §3, §4.

Same contract as the stdio and HTTP-MCP connections (``spawn_and_initialize``,
``request``, the callback setters, ``close``), so the supervisor, discovery,
the per-call gates and the invocation log treat a group like any other server.
There is no process and no MCP peer: ``tools/list`` is answered from the
group's config and ``tools/call`` makes the tool's HTTP request here.

The request is made with no redirect followed (a 3xx is returned as a result,
so the auth header is never carried somewhere nobody configured), the chosen
environment's timeout, and at most 1 MiB of the response read. Each call names
its environment (spec mcp-gateway "Choose a custom tool's environment on every
call"); the connection keeps none, so concurrent calls on different
environments share nothing but the tool definitions. The environment's secrets
are resolved per call by ``env_secrets`` — the guarded resolver for that
environment's base URL — so a missing or unapproved secret stops only calls in
that environment; a value is masked out of every result before it leaves this
module.

An answer is judged by the HTTP status (400 or more fails) and then by the
tool's response rules (``domain/mcp/http_api_response``): a 200 whose header or
JSON field says the API failed is an error result, explained with the value
read and the API's own message. The result names the headers the group asked
to see, every diagnostic header when the call failed, and says when the body
was empty.

The base URL is an endpoint the user configured as their own, so these calls
are exempt from the SSRF guard (Principles → Network defaults).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import mcp.types as mcp_types
from mcp import MCPError

from coffer.application.mcp.call_content import publish_exchange
from coffer.domain.error_base import CofferError
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_environment import (
    HttpApiEnvironment,
    advertised_schema,
    select_environment,
)
from coffer.domain.mcp.http_api_render import ArgumentsInvalid, RenderedRequest, RenderError
from coffer.domain.mcp.http_api_request import build_request
from coffer.domain.mcp.http_api_response import SENSITIVE_HEADERS, judge
from coffer.domain.secret_errors import SecretBindingPending
from coffer.infrastructure.mcp.http_api_exchange import request_record, response_record
from coffer.infrastructure.mcp.http_api_outcome import (
    DIAGNOSTIC_HEADERS,
    MAX_RESPONSE_BYTES,
    HttpCallOutcome,
    ResponseCheck,
    diagnostic_headers,
    mask_secrets,
    response_check,
)

NotificationCallback = Callable[[Any], Awaitable[None]]
#: Resolve one environment's secret headers: ``{header: value}``. Raises
#: ``SecretMissing`` / ``SecretBindingPending`` for that environment only.
EnvSecrets = Callable[[HttpApiEnvironment], Awaitable[dict[str, str]]]


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
                input_schema=advertised_schema(t.input_schema, transport.environments),
                annotations=tool_annotations(t),
            )
            for t in transport.tools
        ]
    )


def _text_result(text: str, *, is_error: bool) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)], is_error=is_error
    )


def overlay_for(env: HttpApiEnvironment, overlay: dict[str, str]) -> dict[str, str]:
    """``{header: value}`` of ``env`` out of an overlay keyed by slot."""
    slots = env.slot_refs()
    return {env.header_of(slot): value for slot, value in overlay.items() if slot in slots}


def refusal_text(error: CofferError | RenderError) -> str:
    """An in-band tool error naming the code, the reason and what to do next."""
    if isinstance(error, ArgumentsInvalid):
        lines = "\n".join(f"- {e.path or '/'} ({e.keyword}): {e.message}" for e in error.errors)
        return f"{error.code}: the arguments do not match the tool's schema\n{lines}"
    if isinstance(error, SecretBindingPending):
        ids = " ".join(error.approval_ids)
        text = f"{error.code}: {error}"
        if ids and error.code == "SECRET_BINDING_PENDING":
            text += f"\napproval ids: {ids}\nnext: coffer approval approve {ids}"
        return text
    code = getattr(error, "code", "CUSTOM_TOOL_REQUEST_INVALID")
    return f"{code}: {error}"


async def send_request(
    request: RenderedRequest,
    *,
    timeout_seconds: float,
    secrets: list[str],
    client_factory: Callable[[], httpx.AsyncClient] | None = None,
    check: ResponseCheck | None = None,
) -> HttpCallOutcome:
    """Send one request and judge the answer by ``check``. Raises
    ``UpstreamTimeout``; returns every answer.

    A connection failure is reported as an outcome with status 0 rather than
    raised: the "upstream" is this module, and it is healthy.
    """
    started = time.monotonic()
    check = check or ResponseCheck()
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
            body = mask_secrets(raw.decode(response.encoding or "utf-8", errors="replace"), secrets)
            location = response.headers.get("location") if response.is_redirect else None
            # Rules read the masked headers: a value never leaves this module
            # unmasked, not even inside a failure's explanation.
            masked = {
                k.lower(): mask_secrets(v, secrets)
                for k, v in response.headers.items()
                if k.lower() not in SENSITIVE_HEADERS
            }
            failure = (
                judge(
                    check.rules,
                    status=response.status_code,
                    headers=masked,
                    body=body,
                    truncated=truncated,
                )
                if response.status_code < 400
                else None
            )
            return HttpCallOutcome(
                url=mask_secrets(request.url, secrets),
                status=response.status_code,
                body=body,
                truncated=truncated,
                duration_ms=int((time.monotonic() - started) * 1000),
                content_type=response.headers.get("content-type"),
                location=mask_secrets(location, secrets) if location else None,
                headers=diagnostic_headers(response.headers, secrets, check.headers),
                body_bytes=len(raw),
                rule_failure=failure,
                named=check.headers,
                all_headers={k: mask_secrets(v, secrets) for k, v in response.headers.items()},
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
        env_secrets: EnvSecrets | None = None,
    ) -> None:
        self._transport = transport
        #: ``{slot: value}``, used only when no ``env_secrets`` is given.
        self._overlay = dict(header_overlay)
        self._server_name = server_name
        self._client_factory = client_factory
        self._env_secrets = env_secrets
        self._closed = False

    def use_env_secrets(self, env_secrets: EnvSecrets) -> None:
        """Resolve each call's environment secrets with ``env_secrets`` (the
        supervisor's guarded resolver), instead of the overlay given up front."""
        self._env_secrets = env_secrets

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

    async def _secrets(self, env: HttpApiEnvironment) -> dict[str, str]:
        if self._env_secrets is not None:
            return await self._env_secrets(env) if env.secret_refs else {}
        return overlay_for(env, self._overlay)

    async def _call(self, name: str, arguments: Any) -> mcp_types.CallToolResult:
        tool = self._transport.tool(name)
        if tool is None:
            return _text_result(f"no tool {name!r} in this group", is_error=True)
        try:
            env, args = select_environment(
                self._transport.environments,
                self._server_name,
                arguments if isinstance(arguments, dict) else {},
            )
            # Validate and render BEFORE any secret is decrypted: a call the
            # schema refuses never touches the store.
            build_request(self._transport, env, tool, args, {})
            overlay = await self._secrets(env)
        except (CofferError, RenderError) as e:
            return _text_result(refusal_text(e), is_error=True)
        secrets = list(overlay.values())
        try:
            request = build_request(self._transport, env, tool, args, overlay)
        except RenderError as e:
            return _text_result(mask_secrets(refusal_text(e), secrets), is_error=True)
        sent = request_record(request, secrets)
        try:
            outcome = await send_request(
                request,
                timeout_seconds=self._transport.timeout_for(env),
                secrets=secrets,
                client_factory=self._client_factory,
                check=response_check(self._transport, tool),
            )
        except UpstreamTimeout:
            publish_exchange(request=sent, response=None)
            raise
        publish_exchange(request=sent, response=response_record(outcome, MAX_RESPONSE_BYTES))
        return _text_result(outcome.as_text(), is_error=outcome.is_error or outcome.status == 0)

    async def close(self) -> None:
        self._closed = True
        self._overlay.clear()


__all__ = [
    "DIAGNOSTIC_HEADERS",
    "MAX_RESPONSE_BYTES",
    "EnvSecrets",
    "HttpApiUpstreamConnection",
    "HttpCallOutcome",
    "ResponseCheck",
    "build_request",
    "diagnostic_headers",
    "list_tools_result",
    "mask_secrets",
    "overlay_for",
    "refusal_text",
    "response_check",
    "send_request",
    "tool_annotations",
]
