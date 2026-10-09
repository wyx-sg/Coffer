"""Run one draft custom tool for the page's Test (design add-http-custom-tools §9).

Implements ``application.mcp.custom_tool_ports.CustomToolRunnerPort`` with the
same request building and sending the gateway uses, so a test shows exactly
what an agent's call would send and get back — masking and the 1 MiB cap
included. Nothing is recorded: a test is not an agent's call.

A request of a group that is not saved yet is a probe of a URL typed into a
form, so its base URL passes the SSRF guard first (Principles → Network
defaults); a saved group's base URL is an endpoint the user configured as
their own and does not.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from coffer.application.mcp.custom_tool_ports import ToolTestOutcome
from coffer.domain.errors import UpstreamTimeout
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_environment import HttpApiEnvironment
from coffer.domain.mcp.http_api_render import RenderError
from coffer.infrastructure.mcp.http_api_client import (
    build_request,
    mask_secrets,
    response_check,
    send_request,
)
from coffer.infrastructure.net.ssrf_guard import check_url


class HttpApiToolRunner:
    async def run(
        self,
        transport: HttpApiTransport,
        env: HttpApiEnvironment,
        tool: HttpApiTool,
        arguments: dict[str, Any],
        overlay: dict[str, str],
    ) -> ToolTestOutcome:
        secrets = list(overlay.values())
        started = time.monotonic()
        try:
            request = build_request(transport, env, tool, arguments, overlay)
        except RenderError as e:
            return ToolTestOutcome(
                ok=False, duration_ms=0, error=mask_secrets(str(e), secrets), failure="request"
            )
        try:
            outcome = await send_request(
                request,
                timeout_seconds=transport.timeout_for(env),
                secrets=secrets,
                check=response_check(transport, tool),
            )
        except UpstreamTimeout as e:
            return ToolTestOutcome(
                ok=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                url=mask_secrets(request.url, secrets),
                error=str(e),
                failure="timeout",
            )
        if outcome.status == 0:
            return ToolTestOutcome(
                ok=False,
                duration_ms=outcome.duration_ms,
                url=outcome.url,
                error=outcome.body,
                failure="connect",
            )
        return ToolTestOutcome(
            ok=not outcome.is_error,
            duration_ms=outcome.duration_ms,
            url=outcome.url,
            status=outcome.status,
            status_line=outcome.status_line(),
            body=outcome.body,
            truncated=outcome.truncated,
            content_type=outcome.content_type,
            response_headers=outcome.headers,
            body_bytes=outcome.body_bytes,
            rule_failure=outcome.rule_failure,
        )

    async def run_unsaved(
        self,
        transport: HttpApiTransport,
        env: HttpApiEnvironment,
        tool: HttpApiTool,
        arguments: dict[str, Any],
    ) -> ToolTestOutcome:
        try:
            await asyncio.to_thread(check_url, str(env.base_url))
        except ValueError as e:
            return ToolTestOutcome(
                ok=False,
                duration_ms=0,
                url=str(env.base_url),
                error=str(e),
                failure="blocked",
            )
        return await self.run(transport, env, tool, arguments, {})


__all__ = ["HttpApiToolRunner"]
