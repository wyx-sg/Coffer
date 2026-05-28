"""Aggregate list operations (tools/list, resources/list, prompts/list).

Extracted from gateway.py for separation and to keep the session class
under its file-size budget. The fan-out and per-server budget policy
lives here; the session simply calls these helpers.

Two design decisions matter:

1. Per-server budget (PER_SERVER_LIST_TIMEOUT): one dead upstream must
   not delay the whole list. The supervisor's retry ladder is meant for
   sticky background recovery, not interactive lists — left unbounded
   it would stall the response for up to ~150 s.

2. Parallel fan-out: with N servers and a P-second per-server budget,
   a serial loop would take up to N*P seconds; gather() keeps it near
   max(times) ≈ P. Without this, two fresh-spawn servers crossed 10 s
   and tripped client read timeouts (concurrent_clients spec).

On per-server timeout / unavailable: log + drop. The supervisor's
retry/cooldown continues in the background; on subsequent calls the
dead server is in cooldown and short-circuits to UpstreamUnavailable.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable

_logger = logging.getLogger(__name__)

# Hard ceiling on how long a single upstream's discovery call may delay an
# aggregate list response. Must accommodate a typical cold spawn +
# initialize round-trip (~1-2 s for a stdio server) but cannot stretch
# to the supervisor's full retry budget.
PER_SERVER_LIST_TIMEOUT = 5.0


EnsureSubscribed = Callable[[str], Awaitable[None]]


async def _one(
    server: str,
    fetcher: Callable[[str], Awaitable[Any]],
    ensure_subscribed: EnsureSubscribed,
    failure_event: str,
) -> Any:
    try:
        result = await asyncio.wait_for(fetcher(server), timeout=PER_SERVER_LIST_TIMEOUT)
        await ensure_subscribed(server)
    except (UpstreamUnavailable, UpstreamTimeout, TimeoutError) as e:
        _logger.warning(failure_event, extra={"server": server, "error": str(e)})
        return None
    return result


async def list_tools_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> dict[str, Any]:
    event = "mcp.gateway.list_tools.upstream_failed"
    results = await asyncio.gather(
        *(_one(s, discovery.list_tools, ensure_subscribed, event) for s in servers)
    )
    all_tools: list[dict[str, Any]] = []
    for batch in results:
        if batch is None:
            continue
        all_tools.extend(
            {
                "name": t.prefixed_name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in batch
        )
    return {"tools": all_tools}


async def list_resources_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> dict[str, Any]:
    results = await asyncio.gather(
        *(
            _one(
                s,
                discovery.list_resources,
                ensure_subscribed,
                "mcp.gateway.list_resources.upstream_failed",
            )
            for s in servers
        )
    )
    all_resources: list[dict[str, Any]] = []
    for batch in results:
        if batch is None:
            continue
        for r in batch:
            entry: dict[str, Any] = {"uri": r.prefixed_uri}
            if r.name is not None:
                entry["name"] = r.name
            if r.description is not None:
                entry["description"] = r.description
            if r.mime_type is not None:
                entry["mimeType"] = r.mime_type
            all_resources.append(entry)
    return {"resources": all_resources}


async def list_prompts_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> dict[str, Any]:
    results = await asyncio.gather(
        *(
            _one(
                s,
                discovery.list_prompts,
                ensure_subscribed,
                "mcp.gateway.list_prompts.upstream_failed",
            )
            for s in servers
        )
    )
    all_prompts: list[dict[str, Any]] = []
    for batch in results:
        if batch is None:
            continue
        for p in batch:
            entry: dict[str, Any] = {"name": p.prefixed_name}
            if p.description is not None:
                entry["description"] = p.description
            if p.arguments:
                entry["arguments"] = p.arguments
            all_prompts.append(entry)
    return {"prompts": all_prompts}
