"""Shared MCP method → SDK-session dispatch table.

Both upstream transports (stdio in ``subprocess.py``, HTTP/SSE in
``http_client.py``) speak to the same ``mcp.ClientSession`` API; they used to
carry near-byte-identical private ``_dispatch_method`` copies, which had
already drifted once (stdio forwarded ``progress_callback``, HTTP didn't).
One table here keeps the transports in lockstep.
"""

from __future__ import annotations

from typing import Any

from mcp.types import PaginatedRequestParams

from coffer.domain.errors import UpstreamUnavailable

#: The most pages one listing follows. An upstream that keeps handing back a
#: cursor must not keep the gateway reading forever.
_MAX_PAGES = 100


async def _all_pages(fetch: Any, items: str) -> Any:
    """Read every page of a ``*/list`` answer and return it as one result.

    An upstream that paginates (MCP "Pagination": ``nextCursor`` in the result,
    ``params.cursor`` in the next request) would otherwise lose every
    capability after its first page.
    """
    result = await fetch(None)
    cursor = getattr(result, "next_cursor", None)
    if not cursor:
        return result
    seen: set[str] = set()
    for _ in range(_MAX_PAGES - 1):
        if not cursor or cursor in seen:
            break
        seen.add(cursor)
        page = await fetch(PaginatedRequestParams(cursor=cursor))
        setattr(result, items, [*getattr(result, items), *getattr(page, items)])
        cursor = page.next_cursor
    result.next_cursor = None
    return result


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
        return await _all_pages(lambda p: session.list_tools(params=p), "tools")
    if method == "tools/call":
        # ``read_timeout_seconds`` bounds the call. The gateway sends no
        # progress token, so an upstream reports no progress and nothing
        # extends the budget: a call that outlasts the server's request timeout
        # is answered as a timeout. A caller of this table that passes a
        # ``progress_callback`` (a test) gets the SDK's progress events.
        return await session.call_tool(
            params["name"],
            arguments=params.get("arguments"),
            read_timeout_seconds=request_timeout_seconds,
            progress_callback=progress_callback,
        )
    if method == "resources/list":
        return await _all_pages(lambda p: session.list_resources(params=p), "resources")
    if method == "resources/read":
        return await session.read_resource(params["uri"])
    if method == "prompts/list":
        return await _all_pages(lambda p: session.list_prompts(params=p), "prompts")
    if method == "prompts/get":
        return await session.get_prompt(params["name"], arguments=params.get("arguments"))
    raise UpstreamUnavailable(f"method not supported by gateway: {method!r}")
