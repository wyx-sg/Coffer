"""Applies the ADR-046 tiering policy to an aggregated tools/list result.

Kept out of ``gateway.py`` so that file stays under its 400-LOC ceiling. The
policy itself is pure and lives in ``domain.mcp.tool_tiering``; this module
only supplies it with usage counts and enforces the fail-open rule.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX
from coffer.application.mcp.ports import MCPInvocationRepoPort
from coffer.application.mcp.tiering_config import TieringConfig
from coffer.domain.mcp.tool_tiering import TieringResult, select_listed_tools

_logger = logging.getLogger(__name__)


async def apply_tiering(
    tools: list[dict[str, Any]],
    *,
    invocations: MCPInvocationRepoPort,
    config: TieringConfig,
    clock: Callable[[], datetime],
) -> TieringResult:
    """Return the slice of ``tools`` to list, per ADR-046.

    Fails open: when tiering is off, or the usage query raises, every tool is
    listed. A broken statistics layer must never be able to hide tools — that
    would turn a monitoring problem into a capability outage.
    """
    if not config.enabled:
        return TieringResult(listed=list(tools), hidden_count=0)

    since = clock() - timedelta(days=config.window_days)
    try:
        usage = await invocations.usage_counts(since=since)
    except Exception:
        _logger.warning(
            "mcp.gateway.tiering.usage_query_failed — listing the full catalogue",
            exc_info=True,
        )
        return TieringResult(listed=list(tools), hidden_count=0)

    return select_listed_tools(
        tools,
        usage,
        builtin_prefix=COFFER_TOOL_PREFIX,
        budget=config.budget,
    )


__all__ = ["apply_tiering"]
