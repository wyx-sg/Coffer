"""The date ranges the Usage page and ``coffer usage`` ask for.

A range is a span of LOCAL calendar days, both ends inclusive, because the
daily rollup (``usage_daily``) is keyed by the local day an attempt started on:
"today" is the user's today, not UTC's. :func:`resolve_range` turns a range
name into those bounds given ``now`` and a time zone, so it is pure and
testable; :meth:`DateRange.utc_bounds` gives the matching instants for a query
over the per-request detail.

Names: ``today``; ``7d`` and ``30d`` (today and the days before it, 7 or 30 in
all); ``month`` (the first of this calendar month through today); ``custom``
(``start`` … ``end``, inclusive, both required).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from enum import StrEnum


class RangeName(StrEnum):
    TODAY = "today"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    MONTH = "month"
    CUSTOM = "custom"


class InvalidRange(ValueError):  # noqa: N818
    """A range that names no span: an unknown name, a custom range missing an
    end, or one that ends before it starts."""


@dataclass(frozen=True)
class DateRange:
    """Local days ``start`` … ``end``, both inclusive."""

    start: date
    end: date
    tz: tzinfo

    @property
    def start_day(self) -> str:
        return self.start.isoformat()

    @property
    def end_day(self) -> str:
        return self.end.isoformat()

    def utc_bounds(self) -> tuple[datetime, datetime]:
        """``[from, to)`` in UTC: local midnight of ``start`` to local
        midnight after ``end``."""
        lo = datetime.combine(self.start, time.min, tzinfo=self.tz)
        hi = datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=self.tz)
        return lo.astimezone(UTC), hi.astimezone(UTC)


def local_day(instant: datetime, tz: tzinfo) -> str:
    """The local ``YYYY-MM-DD`` an instant falls on (a naive instant is UTC)."""
    aware = instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)
    return aware.astimezone(tz).date().isoformat()


def resolve_range(
    name: str,
    *,
    now: datetime,
    tz: tzinfo,
    start: date | None = None,
    end: date | None = None,
) -> DateRange:
    """The local-day span ``name`` means at ``now`` in ``tz``."""
    try:
        kind = RangeName(name)
    except ValueError:
        choices = ", ".join(r.value for r in RangeName)
        raise InvalidRange(f"unknown range {name!r}; expected one of {choices}") from None
    today = (now if now.tzinfo is not None else now.replace(tzinfo=UTC)).astimezone(tz).date()
    if kind is RangeName.TODAY:
        return DateRange(today, today, tz)
    if kind is RangeName.LAST_7_DAYS:
        return DateRange(today - timedelta(days=6), today, tz)
    if kind is RangeName.LAST_30_DAYS:
        return DateRange(today - timedelta(days=29), today, tz)
    if kind is RangeName.MONTH:
        return DateRange(today.replace(day=1), today, tz)
    if start is None or end is None:
        raise InvalidRange("a custom range needs both from and to")
    if end < start:
        raise InvalidRange(f"the range ends ({end}) before it starts ({start})")
    return DateRange(start, end, tz)


__all__ = ["DateRange", "InvalidRange", "RangeName", "local_day", "resolve_range"]
