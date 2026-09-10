"""Environment-sourced knobs for tool tiering (ADR budget-driven-tool-tiering).

Follows the repo's existing env-var tuning pattern (cf.
``COFFER_MCP_SESSION_IDLE_S``). No DB table and no CRUD surface: these are
operator escape hatches, not user-facing settings.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from coffer.domain.mcp.tool_tiering import DEFAULT_BUDGET, DEFAULT_WINDOW_DAYS

MODE_ENV = "COFFER_TOOL_TIERING"
BUDGET_ENV = "COFFER_TOOL_TIERING_BUDGET"
WINDOW_ENV = "COFFER_TOOL_TIERING_WINDOW_DAYS"


@dataclass(frozen=True)
class TieringConfig:
    enabled: bool
    budget: int
    window_days: int


def _positive_int(raw: str | None, default: int) -> int:
    """Parse a positive int, falling back to ``default`` on anything else.

    A malformed knob must never be able to shrink the listed catalogue to
    nothing — misconfiguration degrades to the documented default.
    """
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def load_tiering_config(env: Mapping[str, str] | None = None) -> TieringConfig:
    source: Mapping[str, str] = os.environ if env is None else env
    # Only the explicit "off" disables tiering: a typo must not silently
    # restore the pre-tiering full-catalogue listing.
    enabled = source.get(MODE_ENV, "auto").strip().lower() != "off"
    return TieringConfig(
        enabled=enabled,
        budget=_positive_int(source.get(BUDGET_ENV), DEFAULT_BUDGET),
        window_days=_positive_int(source.get(WINDOW_ENV), DEFAULT_WINDOW_DAYS),
    )


__all__ = [
    "BUDGET_ENV",
    "MODE_ENV",
    "WINDOW_ENV",
    "TieringConfig",
    "load_tiering_config",
]
