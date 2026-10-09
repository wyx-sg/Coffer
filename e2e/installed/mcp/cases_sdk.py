"""The official MCP SDK opens a session against the installed daemon over
Streamable HTTP: the handshake, a call to a synthetic upstream, and the
notification stream (SSE) carrying an upstream's list-changed notifications.

What the gateway does with each message is pinned by the repository's own
suites; here the point is that the frozen daemon's HTTP stack, its session
store and its SSE stream work as shipped.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from e2e.installed.mcp.context import Ctx

A, B = "qa-mcp-a", "qa-mcp-b"
LIST_CHANGED = [f"notifications/{k}/list_changed" for k in ("tools", "resources", "prompts")]


@asynccontextmanager
async def http_session(ctx: Ctx, **callbacks: Any) -> Any:
    """An official-SDK ClientSession over the target's Streamable HTTP ``/mcp``."""
    import httpx2
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"X-Coffer-Token": ctx.run.target.token}
    async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
        url = ctx.run.target.base_url + "/mcp"
        async with (
            streamable_http_client(url, http_client=http) as (r, w),
            ClientSession(r, w, read_timeout_seconds=30, **callbacks) as client,
        ):
            yield client


def notification_method(message: Any) -> str | None:
    """The method of an incoming notification, whichever model the SDK wraps it in."""
    for candidate in (message, getattr(message, "root", None)):
        method = getattr(candidate, "method", None)
        if isinstance(method, str):
            return method
    return None


async def run(ctx: Ctx) -> None:
    seen: list[str] = []

    async def on_message(message: Any) -> None:
        method = notification_method(message)
        if method:
            seen.append(method)

    async with http_session(ctx, message_handler=on_message) as client:
        init = await client.initialize()
        listing = await client.list_tools()
        before = ctx.count(B, name="echo")
        result = await client.call_tool(f"{B}__echo", {"text": "qa SDK HTTP"})
        calls = ctx.count(B, name="echo") - before
        sc = result.structured_content or {}
        ctx.facts["server_info_version"] = init.server_info.version
        ctx.rec.record(
            "the official SDK opens a session against the installed daemon over Streamable HTTP",
            "initialize, tools/list and a call to a synthetic stdio upstream over HTTP",
            expected="protocol 2025-06-18, a non-empty list, qa-mcp-b's echo answers with its "
            "tag and reaches the upstream once",
            actual={
                "protocol": init.protocol_version,
                "server": [init.server_info.name, init.server_info.version],
                "tools": len(listing.tools),
                "structured": sc,
                "upstream_calls": calls,
            },
            ok=init.protocol_version == "2025-06-18"
            and bool(listing.tools)
            and sc.get("tag") == B
            and not result.is_error
            and calls == 1,
            upstream=calls,
        )
        await client.call_tool(f"{A}__mutate", {})
        for _ in range(50):
            if all(m in seen for m in LIST_CHANGED):
                break
            await asyncio.sleep(0.1)
        after = await client.list_tools()
        names = [t.name for t in after.tools]
    ctx.rec.record(
        "upstream tool list changes mid-session",
        "an upstream's list-changed notifications reach the SDK client over the SSE stream",
        expected="tools, resources and prompts list_changed arrive on the session's stream",
        actual={"notifications": seen, "lists_added": f"{A}__added" in names},
        ok=all(m in seen for m in LIST_CHANGED),
    )
