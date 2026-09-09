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

On per-server timeout / unavailable: log the server and error, then leave
that server out of the batch and NAME it in the outcome (ADR-046). The
supervisor's retry/cooldown continues in the background; the session uses
the named failures to retry and tell the client to re-list, because a
client that cached the truncated list will otherwise never see those tools
again this session.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.domain.errors import (
    CredentialLocked,
    CredentialMissing,
    UpstreamTimeout,
    UpstreamUnavailable,
)

_logger = logging.getLogger(__name__)

# Hard ceiling on how long a single upstream's discovery call may delay an
# aggregate list response. Must accommodate a typical cold spawn +
# initialize round-trip (~1-2 s for a stdio server) but cannot stretch
# to the supervisor's full retry budget.
PER_SERVER_LIST_TIMEOUT = 5.0


EnsureSubscribed = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class AggregateOutcome:
    """One aggregate list plus the servers that could not be reached.

    ADR-046: a caller that knows WHICH servers failed can retry them and tell
    the client to re-list. Returning only the survivors made a slow cold spawn
    cost the client that server for the whole session, because the correcting
    list_changed would have to come from the server that never connected.
    """

    items: list[dict[str, Any]]
    failed_servers: list[str]


async def _one(
    server: str,
    fetcher: Callable[[str], Awaitable[Any]],
    ensure_subscribed: EnsureSubscribed,
    failure_event: str,
) -> Any:
    try:
        result = await asyncio.wait_for(fetcher(server), timeout=PER_SERVER_LIST_TIMEOUT)
        await ensure_subscribed(server)
    except (
        UpstreamUnavailable,
        UpstreamTimeout,
        TimeoutError,
        # Unresolvable credentials (locked OS keychain, missing ref) surface
        # when the fetch cold-spawns the upstream; they are that server's
        # problem alone and must not take down the whole aggregate.
        CredentialLocked,
        CredentialMissing,
    ) as e:
        # Rendered into the message, not extra=: the configured log format does
        # not emit extra fields, so the previous call site produced warnings
        # that said only that something, somewhere, had failed.
        _logger.warning(
            "%s server=%s error=%s: %s",
            failure_event,
            server,
            type(e).__name__,
            e,
        )
        return None
    return result


def _tool_entry(t: Any) -> dict[str, Any]:
    return {
        "name": t.prefixed_name,
        "description": t.description,
        "inputSchema": t.input_schema,
    }


def _resource_entry(r: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"uri": r.prefixed_uri}
    if r.name is not None:
        entry["name"] = r.name
    if r.description is not None:
        entry["description"] = r.description
    if r.mime_type is not None:
        entry["mimeType"] = r.mime_type
    return entry


def _prompt_entry(p: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": p.prefixed_name}
    if p.description is not None:
        entry["description"] = p.description
    if p.arguments:
        entry["arguments"] = p.arguments
    return entry


async def _aggregate(
    fetcher: Callable[[str], Awaitable[Any]],
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
    *,
    failure_event: str,
    project: Callable[[Any], dict[str, Any]],
) -> AggregateOutcome:
    """Shared parallel fan-out: discover each server under the per-server
    budget, record failed batches, then flatten via ``project`` into one list.
    The three public functions differ only in (fetcher, event, project)."""
    results = await asyncio.gather(
        *(_one(s, fetcher, ensure_subscribed, failure_event) for s in servers)
    )
    items: list[dict[str, Any]] = []
    failed: list[str] = []
    for server, batch in zip(servers, results, strict=True):
        if batch is None:
            failed.append(server)
            continue
        items.extend(project(x) for x in batch)
    return AggregateOutcome(items=items, failed_servers=failed)


async def list_tools_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> AggregateOutcome:
    """Returns the outcome, not a bare list: the tools path is the one that
    needs to know which servers failed so it can retry them (ADR-046)."""
    return await _aggregate(
        discovery.list_tools,
        ensure_subscribed,
        servers,
        failure_event="mcp.gateway.list_tools.upstream_failed",
        project=_tool_entry,
    )


async def list_resources_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> dict[str, Any]:
    outcome = await _aggregate(
        discovery.list_resources,
        ensure_subscribed,
        servers,
        failure_event="mcp.gateway.list_resources.upstream_failed",
        project=_resource_entry,
    )
    return {"resources": outcome.items}


async def list_prompts_across(
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
) -> dict[str, Any]:
    outcome = await _aggregate(
        discovery.list_prompts,
        ensure_subscribed,
        servers,
        failure_event="mcp.gateway.list_prompts.upstream_failed",
        project=_prompt_entry,
    )
    return {"prompts": outcome.items}
