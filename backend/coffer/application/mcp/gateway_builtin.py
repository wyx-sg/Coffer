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
from coffer.application.mcp.gateway_handlers import _safe_error_summary
from coffer.application.mcp.gateway_tool_search import (
    execute_tool_search,
    tool_search_descriptor,
)
from coffer.application.mcp.ports import MCPInvocationRepoPort
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.mcp.capability import MCPInvocation

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
    so retention + audit work uniformly. `resource_name` is the sentinel
    `"coffer"`.
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
        # Honour SC-010: Coffer-authored errors keep their message; arbitrary
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
                resource_name="coffer",
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


def inject_session_cwd(
    builtin: BuiltinToolRegistry,
    prefixed_name: str,
    params: dict[str, Any],
    session_cwd: str | None,
) -> dict[str, Any]:
    """Thread the session's launch cwd into a built-in tool call.

    Generic: a tool opts in by declaring a ``cwd`` property in its input
    schema (the memory tools do). The gateway never special-cases the memory
    kind (Contract 5/6). A client-supplied ``cwd`` is left untouched. When
    the session never reported a cwd, NOTHING is injected — scope resolution
    then rejects project scope / serves global only, which is correct; the
    daemon's own cwd would silently scope agent memory to whatever project
    the daemon happens to run in."""
    tool = builtin.get(prefixed_name)
    if tool is None:
        return params
    props = tool.input_schema.get("properties", {})
    if not isinstance(props, dict) or "cwd" not in props:
        return params
    args = dict(params.get("arguments") or {})
    if not args.get("cwd") and session_cwd:
        args["cwd"] = session_cwd
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
    embedder: Any | None = None,
) -> dict[str, Any]:
    """Run ``coffer__search_tools`` over ``aggregated_tools``; log + wrap.

    When ``embedder`` is set the ranking is semantic; otherwise BM25 (ADR-024).
    """
    started = clock()
    try:
        args = params.get("arguments") or {}
        result = await execute_tool_search(args, aggregated_tools, embedder)
        # Capture the (intent -> ranked tools) shape for the eval flywheel.
        # Best-effort and opt-in (ADR-019); a no-op unless COFFER_EVAL_CAPTURE is
        # set. ``query`` is a validated non-empty str by the time we get here.
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
