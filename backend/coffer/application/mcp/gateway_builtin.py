"""Helpers for dispatching Coffer built-in MCP tools and recording their
invocations in `mcp_invocations`. Extracted from `gateway.py` to keep that
file under the project's 400-LOC ceiling.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX, BuiltinToolRegistry
from coffer.application.mcp.gateway_handlers import _safe_error_summary
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
        return result
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
        raise


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
