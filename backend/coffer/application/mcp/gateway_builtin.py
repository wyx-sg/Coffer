"""Helpers for dispatching Coffer built-in MCP tools and recording their
invocations in `mcp_invocations`. Extracted from `gateway.py` to keep that
file under the project's 400-LOC ceiling.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.eval_capture import record_tool_search
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway_aggregate_lists import EnsureSubscribed, list_tools_across
from coffer.application.mcp.gateway_handlers import _safe_error_summary
from coffer.application.mcp.gateway_tool_search import (
    execute_tool_search,
    tool_search_descriptor,
)
from coffer.application.mcp.ports import MCPInvocationRepoPort
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceNotFound, UpstreamUnavailable
from coffer.domain.mcp.capability import BUILTIN_SERVER_UID, MCPInvocation

_logger = logging.getLogger(__name__)


async def dispatch_builtin_tool(
    *,
    prefixed_name: str,
    params: dict[str, Any],
    builtin: BuiltinToolRegistry,
    invocations: MCPInvocationRepoPort,
    session_id: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    """Invoke a `coffer__*` built-in tool and record it in mcp_invocations.

    Built-in tools share the same invocation log surface as upstream tools,
    so retention + audit work uniformly. There is no ``mcp_server`` row behind a
    built-in and therefore no uid to record, so the row carries the reserved
    ``BUILTIN_SERVER_UID`` sentinel instead.
    """
    bare_name = prefixed_name[len(COFFER_TOOL_PREFIX) :]
    tool = builtin.get(prefixed_name)
    if tool is None:  # defensive — caller should have gated with is_builtin
        raise UpstreamUnavailable(f"unknown built-in tool: {prefixed_name!r}")

    started = clock()
    try:
        args = params.get("arguments") or {}
        result = await tool.handler(args)
        duration_ms = int((clock() - started).total_seconds() * 1000)
        await _log(
            invocations,
            bare_name,
            started,
            duration_ms,
            status="ok",
            error_message=None,
            session_id=session_id,
        )
        return _to_call_tool_result(result)
    except Exception as exc:
        duration_ms = int((clock() - started).total_seconds() * 1000)
        # No secret in the invocation log (spec credentials "Hold plaintext only
        # in memory at the moment of use"): Coffer-authored errors keep their message; arbitrary
        # downstream exceptions are logged as the class name only, so a built-in
        # tool can never leak args/returned content into the invocation log
        # (matches the upstream path's ``_safe_error_summary`` — finding #7).
        await _log(
            invocations,
            bare_name,
            started,
            duration_ms,
            status="error",
            error_message=_safe_error_summary(exc)[:200],
            session_id=session_id,
        )
        # Per the MCP spec, TOOL-execution failures are in-band ``isError``
        # results the model can read and self-correct from; JSON-RPC errors
        # are reserved for protocol problems (unknown tool, transport).
        return {
            "content": [{"type": "text", "text": _tool_error_text(exc)}],
            "isError": True,
        }


def _tool_error_text(exc: Exception) -> str:
    """The in-band error text shown to the calling agent.

    Coffer-authored messages (``CofferError`` and the handlers' own argument
    ``ValueError``s) are helpful and safe to surface; anything else is reduced
    to its class name so upstream/library messages can't leak content."""
    if isinstance(exc, ValueError):
        return f"{type(exc).__name__}: {exc}"
    return _safe_error_summary(exc)


def _to_call_tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a handler's raw payload as a spec-conforming ``CallToolResult``.

    ``content`` is REQUIRED by the MCP schema — returning the bare payload
    fails SDK validation on every real client. The payload is rendered once as
    text (the universal floor) and kept verbatim in ``structuredContent`` for
    clients that read structured results.
    """
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        # Round-trip through the same dump so a handler returning a non-JSON
        # value (datetime, Path, …) can't blow up response serialization later.
        "structuredContent": json.loads(text),
        "isError": False,
    }


async def _log(
    invocations: MCPInvocationRepoPort,
    bare_name: str,
    started: datetime,
    duration_ms: int,
    *,
    status: str,
    error_message: str | None,
    session_id: str,
) -> None:
    try:
        await invocations.insert(
            MCPInvocation(
                id=None,
                timestamp=started,
                resource_uid=BUILTIN_SERVER_UID,
                capability_type="tool",
                capability_key=bare_name,
                duration_ms=duration_ms,
                status=status,  # type: ignore[arg-type]
                error_message=error_message,
                session_id=session_id,
            )
        )
    except Exception:
        _logger.debug("mcp.gateway.builtin_invocation_log_failed", exc_info=True)


#: The session-scoped values a built-in tool may opt into, named after the
#: input-schema property that declares the opt-in. Kept a fixed list rather
#: than "everything the session knows" so a tool cannot acquire an injected
#: argument by accident.
SESSION_CONTEXT_PROPERTIES = ("cwd",)

#: The argument that tells a built-in tool WHO is calling it. It is not part of
#: any tool's public schema: the value is the gateway's to set, and a client that
#: names one is asking to be someone else.
#:
#: Its value is the agent's **name**, and deliberately not its uid. This is a
#: LABEL, not an identity — the same category as ``audit_log.resource_name``,
#: which records what a thing was called at the time. Its one consumer writes it
#: into the actor column of an audit entry, and an actor column exists to be read
#: by a person; a 32-character hex string there would make the log unreadable by
#: the only audience it has.
#:
#: The uid has its own, separate job in this session — gating what the agent can
#: see, via ``is_active(resource.scope, session_agent_uid)`` — and that job is
#: untouched. Letting one value serve both would be the "one field answering two
#: questions" shape that ADR resource-identity-is-an-immutable-uid exists to
#: remove: a label must follow a rename, an identity must not.
AGENT_ARGUMENT = "agent"


async def agent_actor_label(
    resources: ResourceService,
    session_agent_uid: str | None,
) -> str | None:
    """Resolve the session's agent uid to the NAME a built-in call is labelled with.

    ``None`` — inject nothing — whenever the uid cannot be turned into an agent's
    current name: no identity was reported, the agent has since been deleted, or
    the uid belongs to something that is not an agent. The consumer then records
    an unattributed write, which is honest and readable, where a bare uid would
    be neither: nothing downstream could resolve it later, because the row it
    named is exactly the row that is gone.

    Resolved per call rather than once at the handshake, and not cached. The
    label is meant to say what the agent was called when the write happened, and
    a session outlives a rename; one indexed lookup by uid against local SQLite
    costs nothing beside the tool call it is labelling. There is no row already
    in hand to reuse either — scope gating compares uid strings and never loads
    an agent row.
    """
    if not session_agent_uid:
        return None
    try:
        agent = await resources.get(session_agent_uid)
    except ResourceNotFound:
        return None
    return agent.name if agent.kind == "agent" else None


def inject_session_context(
    builtin: BuiltinToolRegistry,
    prefixed_name: str,
    params: dict[str, Any],
    *,
    session_cwd: str | None,
    agent_label: str | None,
) -> dict[str, Any]:
    """Thread what the session knows about its caller into a built-in call.

    Two arguments, two rules. ``agent`` names the caller (spec mcp-gateway "Take the
    agent identity from the handshake"), so it is ALWAYS the session's: whatever the
    client sent under that name is dropped — unconditionally, including when this
    session has no label of its own to put there — and the label resolved from the
    handshake identity is written in its place. With no label the argument is simply
    absent, and the tool treats the caller as unidentified rather than as whoever it
    claimed to be. See ``AGENT_ARGUMENT`` for why the label is the agent's name and not
    the uid the scope gate compares. ``cwd`` is context a tool opts into by declaring
    the property in its input schema; a client-supplied value is respected and a value
    the session never learned is NOT invented, because the daemon's own cwd would scope
    an agent's work to whatever project the daemon happens to run in.

    Generic: the gateway never special-cases a kind (Contract 5/6) — it only
    matches property names, so a new kind gets this for free and this module
    stays free of any kind's vocabulary."""
    tool = builtin.get(prefixed_name)
    if tool is None:
        return params
    args = dict(params.get("arguments") or {})
    args.pop(AGENT_ARGUMENT, None)
    if agent_label:
        args[AGENT_ARGUMENT] = agent_label
    props = tool.input_schema.get("properties", {})
    if isinstance(props, dict):
        session_values = {"cwd": session_cwd}
        for prop in SESSION_CONTEXT_PROPERTIES:
            value = session_values[prop]
            if prop in props and value and not args.get(prop):
                args[prop] = value
    return {**params, "arguments": args}


def append_builtin_tools(tools: list[dict[str, Any]], builtin: BuiltinToolRegistry) -> None:
    """Append Coffer's own built-in tools + the tool-search meta-tool to a
    ``tools/list`` result (kept here so the gateway session stays small)."""
    for bt in builtin.list():
        tools.append(
            {
                "name": f"{COFFER_TOOL_PREFIX}{bt.name}",
                "description": bt.description,
                "inputSchema": bt.input_schema,
            }
        )
    tools.append(tool_search_descriptor())


async def dispatch_tool_search(
    *,
    params: dict[str, Any],
    aggregated_tools: list[dict[str, Any]],
    invocations: MCPInvocationRepoPort,
    session_id: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    """Run ``coffer__search_tools`` over ``aggregated_tools``; log + wrap."""
    started = clock()
    try:
        args = params.get("arguments") or {}
        result = await execute_tool_search(args, aggregated_tools)
        # Capture the (intent -> ranked tools) shape for the eval flywheel.
        # Best-effort and opt-in (ADR eval-capture-and-regression-gate); a no-op unless
        # COFFER_EVAL_CAPTURE is set. ``query`` is a validated non-empty str by
        # the time we get here.
        record_tool_search(args["query"], [t["name"] for t in result["tools"]])
        duration_ms = int((clock() - started).total_seconds() * 1000)
        await _log(
            invocations,
            "search_tools",
            started,
            duration_ms,
            status="ok",
            error_message=None,
            session_id=session_id,
        )
        return _to_call_tool_result(result)
    except Exception as exc:
        duration_ms = int((clock() - started).total_seconds() * 1000)
        await _log(
            invocations,
            "search_tools",
            started,
            duration_ms,
            status="error",
            error_message=_safe_error_summary(exc)[:200],
            session_id=session_id,
        )
        return {"content": [{"type": "text", "text": _tool_error_text(exc)}], "isError": True}


async def run_tool_search(
    params: dict[str, Any],
    *,
    discovery: CapabilityDiscovery,
    ensure_subscribed: EnsureSubscribed,
    servers: list[str],
    invocations: MCPInvocationRepoPort,
    session_id: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    """Aggregate the catalogue, then search it.

    Deliberately the untiered outcome: search is what makes an unlisted tool
    reachable, so it must see the whole catalogue. Failed servers are ignored
    here rather than recorded as degraded — a search that ranks what is
    reachable is more useful than one that refuses, and ``tools/list`` is the
    path that owns the degraded-server retry.
    """
    outcome = await list_tools_across(discovery, ensure_subscribed, servers)
    return await dispatch_tool_search(
        params=params,
        aggregated_tools=outcome.items,
        invocations=invocations,
        session_id=session_id,
        clock=clock,
    )
