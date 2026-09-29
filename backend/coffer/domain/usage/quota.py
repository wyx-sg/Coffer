"""A subscription agent's OFFICIAL remaining quota, as its own feeds report it
(ADR usage-is-metered-at-the-proxy-and-subscriptions-show-only-official-quota).

Three feeds, one parser each, all to the same :class:`QuotaSnapshot`:

* Codex — ``codex app-server``'s ``account/rateLimits/read`` result and its
  ``account/rateLimits/updated`` notification: ``rateLimits.primary`` (about
  5 h) and ``rateLimits.secondary`` (weekly), each ``usedPercent``,
  ``windowDurationMins``, ``resetsAt`` (epoch seconds). camelCase and
  snake_case are both read — the wire is camelCase, the Rust structs are not.
* Claude Code — the SDK's ``rate_limit_event`` ``rate_limit_info`` dict.
  ``unifiedWindows.{five_hour, seven_day, …}.{utilization, resetsAt}`` gives
  every window when present; it is marked ``@internal``, so without it the
  top-level ``rateLimitType`` / ``utilization`` / ``resetsAt`` (the window
  currently limiting) is read instead — less detail, never a failure.
  ``utilization`` is a 0-1 fraction per the SDK; a value above 1 is taken as
  already a percentage.
* Claude Code's statusLine stdin ``rate_limits`` (documented):
  ``five_hour`` / ``seven_day`` ``{used_percentage, resets_at}``.

Nothing here estimates: a field that is absent is absent, and a feed with no
usable window yields ``None``, not a zero. Pure: no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

CLAUDE_AGENT_TYPE = "claude_code"
CODEX_AGENT_TYPE = "codex"


class QuotaSource(StrEnum):
    CODEX_APP_SERVER = "codex_app_server"
    CLAUDE_RATE_LIMIT_EVENT = "claude_rate_limit_event"
    CLAUDE_STATUSLINE = "claude_statusline"


@dataclass(frozen=True)
class QuotaWindow:
    """One rolling allowance: how much of it is used and when it resets."""

    key: str
    label: str
    used_percent: float
    window_minutes: int | None = None
    resets_at: datetime | None = None


@dataclass(frozen=True)
class QuotaSnapshot:
    """What one feed said about one agent type at ``observed_at``."""

    agent_type: str
    source: QuotaSource
    observed_at: datetime
    windows: tuple[QuotaWindow, ...]
    plan: str | None = None


#: Claude window keys → (label, length in minutes).
_CLAUDE_WINDOWS: dict[str, tuple[str, int | None]] = {
    "five_hour": ("5-hour", 300),
    "seven_day": ("Weekly", 10080),
    "seven_day_opus": ("Weekly (Opus)", 10080),
    "seven_day_sonnet": ("Weekly (Sonnet)", 10080),
    "seven_day_oauth_apps": ("Weekly (apps)", 10080),
    "seven_day_overage_included": ("Weekly (with extra usage)", 10080),
    "overage": ("Extra usage", None),
}


def _get(obj: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in obj and obj[name] is not None:
            return obj[name]
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _clamp(percent: float) -> float:
    return max(0.0, min(100.0, percent))


def _instant(value: Any) -> datetime | None:
    """Epoch seconds (or milliseconds) or an ISO 8601 string, as UTC."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if value > 1e11 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def window_label(minutes: int | None, fallback: str) -> str:
    """A human label for a window length: ``5-hour``, ``Weekly``, ``30-day``."""
    if minutes is None or minutes <= 0:
        return fallback
    if minutes == 10080:
        return "Weekly"
    if minutes % 1440 == 0:
        return f"{minutes // 1440}-day"
    if minutes % 60 == 0:
        return f"{minutes // 60}-hour"
    return f"{minutes}-minute"


def _snapshot(
    agent_type: str,
    source: QuotaSource,
    observed_at: datetime,
    windows: list[QuotaWindow],
    plan: Any = None,
) -> QuotaSnapshot | None:
    if not windows:
        return None
    return QuotaSnapshot(
        agent_type=agent_type,
        source=source,
        observed_at=observed_at,
        windows=tuple(windows),
        plan=plan if isinstance(plan, str) and plan else None,
    )


# -- Codex ---------------------------------------------------------------------


def _codex_window(key: str, raw: Any) -> QuotaWindow | None:
    if not isinstance(raw, Mapping):
        return None
    used = _number(_get(raw, "usedPercent", "used_percent"))
    if used is None:
        return None
    minutes_raw = _number(_get(raw, "windowDurationMins", "window_duration_mins"))
    minutes = int(minutes_raw) if minutes_raw is not None else None
    return QuotaWindow(
        key=key,
        label=window_label(minutes, key),
        used_percent=_clamp(used),
        window_minutes=minutes,
        resets_at=_instant(_get(raw, "resetsAt", "resets_at")),
    )


def from_codex_rate_limits(
    payload: Mapping[str, Any], *, observed_at: datetime
) -> QuotaSnapshot | None:
    """Parse an ``account/rateLimits/read`` result or an
    ``account/rateLimits/updated`` notification's params (or the bare
    ``RateLimitSnapshot`` itself)."""
    if not isinstance(payload, Mapping):
        return None
    limits = _get(payload, "rateLimits", "rate_limits")
    snap: Mapping[str, Any] = limits if isinstance(limits, Mapping) else payload
    windows = [
        w
        for w in (
            _codex_window("primary", snap.get("primary")),
            _codex_window("secondary", snap.get("secondary")),
        )
        if w is not None
    ]
    plan = _get(snap, "planType", "plan_type") or _get(payload, "planType", "plan_type")
    return _snapshot(CODEX_AGENT_TYPE, QuotaSource.CODEX_APP_SERVER, observed_at, windows, plan)


# -- Claude Code ---------------------------------------------------------------


def _percent_from_utilization(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return _clamp(number * 100 if number <= 1 else number)


def _claude_window(key: str, used: float, resets_at: datetime | None) -> QuotaWindow:
    label, minutes = _CLAUDE_WINDOWS.get(key, (key.replace("_", " "), None))
    return QuotaWindow(
        key=key, label=label, used_percent=used, window_minutes=minutes, resets_at=resets_at
    )


def from_claude_rate_limit_event(
    raw: Mapping[str, Any], *, observed_at: datetime
) -> QuotaSnapshot | None:
    """Parse a ``rate_limit_event``'s raw ``rate_limit_info`` dict."""
    if not isinstance(raw, Mapping):
        return None
    windows: list[QuotaWindow] = []
    unified = _get(raw, "unifiedWindows", "unified_windows")
    if isinstance(unified, Mapping):
        for key, value in unified.items():
            if not isinstance(value, Mapping):
                continue
            used = _percent_from_utilization(value.get("utilization"))
            if used is None:
                continue
            resets = _instant(_get(value, "resetsAt", "resets_at"))
            windows.append(_claude_window(str(key), used, resets))
    if not windows:
        key = _get(raw, "rateLimitType", "rate_limit_type")
        used = _percent_from_utilization(raw.get("utilization"))
        if isinstance(key, str) and key and used is not None:
            resets = _instant(_get(raw, "resetsAt", "resets_at"))
            windows.append(_claude_window(key, used, resets))
    return _snapshot(CLAUDE_AGENT_TYPE, QuotaSource.CLAUDE_RATE_LIMIT_EVENT, observed_at, windows)


def from_statusline(
    rate_limits: Mapping[str, Any], *, observed_at: datetime
) -> QuotaSnapshot | None:
    """Parse the statusLine stdin JSON's ``rate_limits`` object."""
    if not isinstance(rate_limits, Mapping):
        return None
    windows: list[QuotaWindow] = []
    for key, value in rate_limits.items():
        if not isinstance(value, Mapping):
            continue
        used = _number(value.get("used_percentage"))
        if used is None:
            continue
        windows.append(_claude_window(str(key), _clamp(used), _instant(value.get("resets_at"))))
    return _snapshot(CLAUDE_AGENT_TYPE, QuotaSource.CLAUDE_STATUSLINE, observed_at, windows)


__all__ = [
    "CLAUDE_AGENT_TYPE",
    "CODEX_AGENT_TYPE",
    "QuotaSnapshot",
    "QuotaSource",
    "QuotaWindow",
    "from_claude_rate_limit_event",
    "from_codex_rate_limits",
    "from_statusline",
    "window_label",
]
