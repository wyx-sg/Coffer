"""The three official quota feeds parse to one shape, and never estimate."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.usage.quota import (
    QuotaSource,
    from_claude_rate_limit_event,
    from_codex_rate_limits,
    from_statusline,
    window_label,
)

_AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
_RESET = 1790000000


def test_codex_read_result_camel_case() -> None:
    payload = {
        "rateLimits": {
            "primary": {"usedPercent": 42, "windowDurationMins": 300, "resetsAt": _RESET},
            "secondary": {"usedPercent": 7, "windowDurationMins": 10080, "resetsAt": _RESET},
            "planType": "plus",
        }
    }
    snap = from_codex_rate_limits(payload, observed_at=_AT)
    assert snap is not None
    assert snap.agent_type == "codex"
    assert snap.source is QuotaSource.CODEX_APP_SERVER
    assert snap.plan == "plus"
    primary, secondary = snap.windows
    assert (primary.key, primary.label, primary.used_percent) == ("primary", "5-hour", 42.0)
    assert primary.resets_at == datetime.fromtimestamp(_RESET, tz=UTC)
    assert (secondary.label, secondary.window_minutes) == ("Weekly", 10080)


def test_codex_update_notification_snake_case() -> None:
    params = {
        "rate_limits": {
            "primary": {"used_percent": 99.5, "window_duration_mins": 43200, "resets_at": None}
        }
    }
    snap = from_codex_rate_limits(params, observed_at=_AT)
    assert snap is not None
    (only,) = snap.windows
    assert (only.used_percent, only.label, only.resets_at) == (99.5, "30-day", None)


def test_codex_without_windows_is_no_value() -> None:
    assert from_codex_rate_limits({"rateLimits": {"primary": None}}, observed_at=_AT) is None
    assert from_codex_rate_limits({}, observed_at=_AT) is None


def test_claude_event_prefers_unified_windows() -> None:
    raw = {
        "status": "allowed",
        "rateLimitType": "five_hour",
        "utilization": 0.5,
        "resetsAt": _RESET,
        "unifiedWindows": {
            "five_hour": {"utilization": 0.25, "resetsAt": _RESET},
            "seven_day": {"utilization": 0.6, "resetsAt": _RESET + 1},
        },
    }
    snap = from_claude_rate_limit_event(raw, observed_at=_AT)
    assert snap is not None
    assert snap.source is QuotaSource.CLAUDE_RATE_LIMIT_EVENT
    got = {w.key: (w.label, w.used_percent) for w in snap.windows}
    assert got == {"five_hour": ("5-hour", 25.0), "seven_day": ("Weekly", 60.0)}


def test_claude_event_falls_back_to_the_top_level_window() -> None:
    raw = {"status": "allowed_warning", "rateLimitType": "seven_day", "utilization": 0.81}
    snap = from_claude_rate_limit_event(raw, observed_at=_AT)
    assert snap is not None
    (only,) = snap.windows
    assert (only.key, only.used_percent, only.resets_at) == ("seven_day", 81.0, None)


def test_claude_utilization_above_one_is_already_a_percentage() -> None:
    raw = {"rateLimitType": "five_hour", "utilization": 37}
    snap = from_claude_rate_limit_event(raw, observed_at=_AT)
    assert snap is not None and snap.windows[0].used_percent == 37.0


def test_claude_event_with_status_only_degrades_to_no_value() -> None:
    assert from_claude_rate_limit_event({"status": "allowed"}, observed_at=_AT) is None
    assert from_claude_rate_limit_event({"unifiedWindows": "junk"}, observed_at=_AT) is None


def test_statusline_rate_limits() -> None:
    rate_limits = {
        "five_hour": {"used_percentage": 12.5, "resets_at": _RESET},
        "seven_day": {"used_percentage": 140, "resets_at": _RESET},
        "junk": "x",
    }
    snap = from_statusline(rate_limits, observed_at=_AT)
    assert snap is not None
    assert snap.source is QuotaSource.CLAUDE_STATUSLINE
    got = {w.key: w.used_percent for w in snap.windows}
    assert got == {"five_hour": 12.5, "seven_day": 100.0}  # clamped, never over 100
    assert from_statusline({}, observed_at=_AT) is None


@pytest.mark.parametrize(
    ("minutes", "label"),
    [(300, "5-hour"), (10080, "Weekly"), (1440, "1-day"), (90, "90-minute"), (None, "k")],
)
def test_window_label(minutes: int | None, label: str) -> None:
    assert window_label(minutes, "k") == label
