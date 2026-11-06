"""When a scheduled task runs (spec channels "Run a scheduled task at the
times it names").

A schedule is one of a few shapes a person picks from — once, every hour, every
day, on weekdays, once a week — plus a cron expression for anything else, and
``manual`` for a task that runs only when asked. Every time is a wall-clock
time: "every day at 18:00" means 18:00 on the clock on the wall, summer time or
not, so the arithmetic is done on naive wall datetimes and only the result is
turned into an instant. The wall clock is the schedule's own IANA ``timezone``
when it names one, and this machine's otherwise. The two conversions are
injected, which keeps this module pure and lets a test pin a zone; the defaults
read the schedule's zone, or ask the operating system, which knows this
machine's summer-time rules. A wall time a spring-forward change skips runs
once at the first valid time after it (02:30 on that day runs at 03:00).

The one question asked of a schedule is :func:`next_slot`: the first time it
names strictly after a given instant. The scheduler walks it forward to find the
latest slot it missed and the next one to sleep until; nothing else about a
schedule is computed anywhere.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from coffer.domain.channel.cron import next_cron, parse_cron

__all__ = [
    "MIN_REPEAT",
    "CronSchedule",
    "DailySchedule",
    "HourlySchedule",
    "ManualSchedule",
    "OnceSchedule",
    "Schedule",
    "WeekdaysSchedule",
    "WeeklySchedule",
    "conversions",
    "is_repeating",
    "next_slot",
    "parse_cron",
    "shortest_gap",
    "zone_of",
]

#: The shortest gap a repeating schedule may have (spec channels "Run a
#: scheduled task at the times it names"). Every run is a whole agent turn;
#: anything that has to happen more often wants an event, not a timer.
MIN_REPEAT = timedelta(minutes=15)

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _clock(value: str) -> time:
    match = _TIME.match(value)
    if match is None:
        raise ValueError(f"time must be HH:MM (24-hour), got {value!r}")
    return time(int(match.group(1)), int(match.group(2)))


def zone_of(name: str) -> ZoneInfo:
    """The IANA zone ``name``, or ``ValueError`` naming it when there is none."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"unknown timezone {name!r}") from e


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: The IANA zone whose wall clock the times are read on; ``None`` is this
    #: machine's.
    timezone: str | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("timezone")
    @classmethod
    def _zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        zone_of(value)
        return value


class OnceSchedule(_Shape):
    """One run at ``at``, an instant with its offset. The task ends after it."""

    kind: Literal["once"] = "once"
    at: datetime

    @field_validator("at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("`at` must carry a UTC offset")
        return value


class HourlySchedule(_Shape):
    """Every hour, at ``minute`` past."""

    kind: Literal["hourly"] = "hourly"
    minute: int = Field(default=0, ge=0, le=59)


class DailySchedule(_Shape):
    """Every day at ``time`` (local)."""

    kind: Literal["daily"] = "daily"
    time: str

    @field_validator("time")
    @classmethod
    def _time(cls, value: str) -> str:
        _clock(value)
        return value


class WeekdaysSchedule(DailySchedule):
    """Monday to Friday at ``time`` (local)."""

    kind: Literal["weekdays"] = "weekdays"  # type: ignore[assignment]


class WeeklySchedule(DailySchedule):
    """Once a week: ``weekday`` (0 is Monday) at ``time`` (local)."""

    kind: Literal["weekly"] = "weekly"  # type: ignore[assignment]
    weekday: int = Field(ge=0, le=6)


class CronSchedule(_Shape):
    """A five-field cron expression, in local time."""

    kind: Literal["cron"] = "cron"
    expr: str

    @field_validator("expr")
    @classmethod
    def _expr(cls, value: str) -> str:
        parse_cron(value)
        return value.strip()


class ManualSchedule(_Shape):
    """No times at all: the task runs when someone asks it to."""

    kind: Literal["manual"] = "manual"


Schedule = Annotated[
    OnceSchedule
    | HourlySchedule
    | DailySchedule
    | WeekdaysSchedule
    | WeeklySchedule
    | CronSchedule
    | ManualSchedule,
    Field(discriminator="kind"),
]

#: Turns an instant into the naive wall-clock time on this machine, and back.
ToLocal = Callable[[datetime], datetime]
ToInstant = Callable[[datetime], datetime]


def _os_local(instant: datetime) -> datetime:
    return instant.astimezone().replace(tzinfo=None)


def _os_instant(wall: datetime) -> datetime:
    # A naive datetime's ``astimezone`` reads it as local time with the
    # operating system's rules, summer time included.
    return wall.astimezone()


def _zone_local(zone: ZoneInfo) -> ToLocal:
    return lambda instant: instant.astimezone(zone).replace(tzinfo=None)


def _zone_instant(zone: ZoneInfo) -> ToInstant:
    # ``fold=0`` reads a doubled hour as its first instant and a skipped one
    # with the offset before the change, i.e. as a later wall time; the gap
    # itself is handled by :func:`_first_valid`.
    # Through UTC, so the instant carries a fixed offset: arithmetic on an
    # instant still in ``zone`` would be wall-clock arithmetic, and reading it
    # back in ``zone`` would hand the skipped wall time back unchanged.
    return lambda wall: wall.replace(tzinfo=zone).astimezone(UTC)


def conversions(schedule: Schedule) -> tuple[ToLocal, ToInstant]:
    """The wall-clock conversions ``schedule`` is read with: its own zone's,
    or this machine's."""
    if schedule.timezone:
        zone = zone_of(schedule.timezone)
        return _zone_local(zone), _zone_instant(zone)
    return _os_local, _os_instant


def is_repeating(schedule: Schedule) -> bool:
    return not isinstance(schedule, OnceSchedule | ManualSchedule)


# --- the one question -------------------------------------------------------


def _next_wall(schedule: Schedule, after: datetime) -> datetime | None:
    """The first wall-clock time ``schedule`` names strictly after ``after``
    (both naive local)."""
    if isinstance(schedule, HourlySchedule):
        slot = after.replace(minute=schedule.minute, second=0, microsecond=0)
        return slot if slot > after else slot + timedelta(hours=1)
    if isinstance(schedule, CronSchedule):
        return next_cron(parse_cron(schedule.expr), after)
    if isinstance(schedule, DailySchedule):
        at = _clock(schedule.time)
        slot = datetime.combine(after.date(), at)
        if slot <= after:
            slot += timedelta(days=1)
        if isinstance(schedule, WeekdaysSchedule):
            while slot.weekday() >= 5:
                slot += timedelta(days=1)
        elif isinstance(schedule, WeeklySchedule):
            slot += timedelta(days=(schedule.weekday - slot.weekday()) % 7)
        return slot
    return None


#: The widest daylight-saving gap searched for its end.
_GAP_SEARCH = timedelta(hours=4)


def _first_valid(wall: datetime, instant: datetime, to_local: ToLocal) -> datetime:
    """``instant`` if ``wall`` exists; for a wall time a spring-forward change
    skips, the first instant after the gap (02:30 on that day → 03:00).

    A skipped wall time reads back (``to_local``) as a different wall time.
    Before the change every instant reads earlier than ``wall``, after it later,
    so the change itself is the earliest instant reading at or after ``wall``:
    found by bisection to the second."""
    if to_local(instant).replace(microsecond=0) == wall.replace(microsecond=0):
        return instant
    low, high = instant - _GAP_SEARCH, instant + _GAP_SEARCH
    if to_local(low) >= wall or to_local(high) < wall:
        return instant
    while high - low > timedelta(seconds=1):
        middle = low + (high - low) / 2
        if to_local(middle) >= wall:
            high = middle
        else:
            low = middle
    return high.replace(microsecond=0)


def next_slot(
    schedule: Schedule,
    after: datetime,
    *,
    to_local: ToLocal | None = None,
    to_instant: ToInstant | None = None,
) -> datetime | None:
    """The first instant ``schedule`` names strictly after the instant ``after``;
    ``None`` when it names none (manual, or a one-off already behind)."""
    if isinstance(schedule, ManualSchedule):
        return None
    if isinstance(schedule, OnceSchedule):
        return schedule.at if schedule.at > after else None
    own_local, own_instant = conversions(schedule)
    to_local = to_local or own_local
    to_instant = to_instant or own_instant
    wall = _next_wall(schedule, to_local(after))
    while wall is not None:
        # A wall time that exists twice reads as its first instant; one that
        # does not exist runs at the first valid time after it. Either way the
        # slot must still be after ``after``.
        instant = _first_valid(wall, to_instant(wall), to_local)
        if instant > after:
            return instant
        wall = _next_wall(schedule, wall)
    return None


def shortest_gap(
    schedule: Schedule,
    *,
    start: datetime,
    to_local: ToLocal | None = None,
    to_instant: ToInstant | None = None,
    probes: int = 64,
) -> timedelta | None:
    """The shortest gap between consecutive slots over the next ``probes``
    slots from ``start``: what :data:`MIN_REPEAT` is checked against. ``None``
    for a schedule with fewer than two slots."""
    gaps: list[timedelta] = []
    previous = next_slot(schedule, start, to_local=to_local, to_instant=to_instant)
    for _ in range(probes):
        if previous is None:
            break
        following = next_slot(schedule, previous, to_local=to_local, to_instant=to_instant)
        if following is None:
            break
        gaps.append(following - previous)
        previous = following
    return min(gaps) if gaps else None
