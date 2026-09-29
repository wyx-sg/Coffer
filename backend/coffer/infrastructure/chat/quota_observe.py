"""Forward a driven agent's quota report without ever affecting its turn.

Both chat adapters call :func:`forward_quota` from their stream pump when the
agent reports its subscription windows (Claude Code's ``rate_limit_event``,
Codex's ``account/rateLimits/updated``). The observer is bounded by a short
timeout and every failure is logged and swallowed: a quota value is a nicety,
the turn is the product.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from coffer.application.chat.ports import QuotaObserver

_logger = logging.getLogger(__name__)

#: The longest a quota write may hold up the turn's stream.
_OBSERVE_TIMEOUT = 2.0


async def forward_quota(observer: QuotaObserver | None, agent_type: str, payload: Any) -> None:
    """Hand ``payload`` to ``observer`` (if any); never raises."""
    if observer is None or not isinstance(payload, dict):
        return
    try:
        await asyncio.wait_for(observer(agent_type, payload), timeout=_OBSERVE_TIMEOUT)
    except asyncio.CancelledError:
        raise
    except Exception:
        _logger.warning("chat.quota_observe_failed", extra={"agent": agent_type}, exc_info=True)


__all__ = ["forward_quota"]
