"""Range names resolve to local-day spans."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from coffer.domain.usage.ranges import InvalidRange, local_day, resolve_range

_SGT = timezone(timedelta(hours=8))
#: 2026-09-30 23:30 UTC is already 2026-10-01 in Singapore.
_NOW = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)


def test_today_is_the_local_day() -> None:
    span = resolve_range("today", now=_NOW, tz=_SGT)
    assert (span.start, span.end) == (date(2026, 10, 1), date(2026, 10, 1))


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a range resolves in local days",
)
def test_rolling_ranges_include_today() -> None:
    assert resolve_range("7d", now=_NOW, tz=UTC).start == date(2026, 9, 24)
    assert resolve_range("30d", now=_NOW, tz=UTC).start == date(2026, 9, 1)
    assert resolve_range("7d", now=_NOW, tz=UTC).end == date(2026, 9, 30)


def test_month_is_this_calendar_month() -> None:
    assert resolve_range("month", now=_NOW, tz=UTC).start == date(2026, 9, 1)
    assert resolve_range("month", now=_NOW, tz=_SGT).start == date(2026, 10, 1)


def test_custom_range_is_inclusive_and_validated() -> None:
    span = resolve_range("custom", now=_NOW, tz=UTC, start=date(2026, 9, 1), end=date(2026, 9, 3))
    assert (span.start_day, span.end_day) == ("2026-09-01", "2026-09-03")
    with pytest.raises(InvalidRange):
        resolve_range("custom", now=_NOW, tz=UTC, start=date(2026, 9, 1))
    with pytest.raises(InvalidRange):
        resolve_range("custom", now=_NOW, tz=UTC, start=date(2026, 9, 3), end=date(2026, 9, 1))
    with pytest.raises(InvalidRange):
        resolve_range("fortnight", now=_NOW, tz=UTC)


def test_local_day_of_an_instant() -> None:
    assert local_day(_NOW, _SGT) == "2026-10-01"
    assert local_day(_NOW.replace(tzinfo=None), UTC) == "2026-09-30"


def test_the_last_24_hours_spans_the_local_days_its_ends_fall_on() -> None:
    span = resolve_range("24h", now=_NOW, tz=_SGT)
    assert (span.start, span.end) == (date(2026, 9, 30), date(2026, 10, 1))
    span = resolve_range("24h", now=_NOW, tz=UTC)
    assert (span.start, span.end) == (date(2026, 9, 29), date(2026, 9, 30))
