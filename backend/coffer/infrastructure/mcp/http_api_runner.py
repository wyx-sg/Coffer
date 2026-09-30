"""Run one draft custom tool for the page's Test (design add-http-custom-tools §9).

Implements ``application.mcp.custom_tool_ports.CustomToolRunnerPort`` with the
same request building and sending the gateway uses, so a test shows exactly
what an agent's call would send and get back — masking and the 1 MiB cap
included. Nothing is recorded: a test is not an agent's call.
"""

from __future__ import annotations

import time
from typing import Any

from coffer.application.mcp.custom_tool_ports import ToolTestOutcome
from coffer.domain.errors import UpstreamTimeout
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_render import RenderError
from coffer.infrastructure.mcp.http_api_client import build_request, mask_secrets, send_request


class HttpApiToolRunner:
    async def run(
        self,
        transport: HttpApiTransport,
        tool: HttpApiTool,
        arguments: dict[str, Any],
        overlay: dict[str, str],
    ) -> ToolTestOutcome:
        secrets = list(overlay.values())
        started = time.monotonic()
        try:
            request = build_request(transport, tool, arguments, overlay)
        except RenderError as e:
            return ToolTestOutcome(ok=False, duration_ms=0, error=mask_secrets(str(e), secrets))
        try:
            outcome = await send_request(
                request, timeout_seconds=transport.timeout_seconds, secrets=secrets
            )
        except UpstreamTimeout as e:
            return ToolTestOutcome(
                ok=False,
                duration_ms=int((time.monotonic() - started) * 1000),
                url=mask_secrets(request.url, secrets),
                error=str(e),
            )
        if outcome.status == 0:
            return ToolTestOutcome(
                ok=False, duration_ms=outcome.duration_ms, url=outcome.url, error=outcome.body
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
        )


__all__ = ["HttpApiToolRunner"]
