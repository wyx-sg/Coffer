"""Shared MCP method → SDK-session dispatch table.

Both upstream transports (stdio in ``subprocess.py``, HTTP/SSE in
``http_client.py``) speak to the same ``mcp.ClientSession`` API; they used to
carry near-byte-identical private ``_dispatch_method`` copies, which had
already drifted once (stdio forwarded ``progress_callback``, HTTP didn't —
CODE-L2). One table here keeps the transports in lockstep.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from coffer.domain.errors import UpstreamUnavailable


async def dispatch_method(
    session: Any,
    method: str,
    params: dict[str, Any],
    *,
    request_timeout_seconds: float,
    progress_callback: Any | None = None,
) -> Any:
    """Forward one MCP request to an initialized SDK ``ClientSession``."""
    if method == "tools/list":
        return await session.list_tools()
    if method == "tools/call":
        # T-060: pass read_timeout_seconds so the SDK resets the idle timer
        # on every notifications/progress event, preventing premature timeout
        # of long-running tools that stream progress.
        try:
            return await session.call_tool(
                params["name"],
                arguments=params.get("arguments"),
                read_timeout_seconds=timedelta(seconds=request_timeout_seconds),
                progress_callback=progress_callback,
            )
        except TypeError as e:
            # Older SDK build that doesn't accept the optional kwargs. Retry
            # ONLY for that signature mismatch: a TypeError raised after the
            # call started (bad argument shape, SDK-internal bug) must not
            # re-invoke a possibly non-idempotent tool.
            msg = str(e)
            if "read_timeout_seconds" not in msg and "progress_callback" not in msg:
                raise
            return await session.call_tool(params["name"], arguments=params.get("arguments"))
    if method == "resources/list":
        return await session.list_resources()
    if method == "resources/read":
        return await session.read_resource(params["uri"])
    if method == "prompts/list":
        return await session.list_prompts()
    if method == "prompts/get":
        return await session.get_prompt(params["name"], arguments=params.get("arguments"))
    raise UpstreamUnavailable(f"method not supported by gateway: {method!r}")
