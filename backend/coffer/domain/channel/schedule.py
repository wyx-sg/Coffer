"""When a scheduled task runs (spec channels "Run a scheduled task at the times
it names").

A schedule is one of a few shapes a person picks from — once, every hour, every
day, on weekdays, once a week — plus a cron expression for anything else, and
``manual`` for a task that runs only when asked. Every time is this machine's
local time: "every day at 18:00" means 18:00 on the clock on the wall, summer
time or not, so the arithmetic is done on naive local datetimes and only the
result is turned into an instant. The two conversions are injected, which keeps
this module pure and lets a test pin a zone; the defaults ask the operating
system, which knows this machine's summer-time rules.

The one question asked of a schedule is :func:`next_slot`: the first time it
names strictly after a given instant. The scheduler walks it forward to find the
latest slot it missed and the next one to sleep until; nothing else about a
schedule is computed anywhere.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    "is_repeating",
    "next_slot",
    "parse_cron",
    "shortest_gap",
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


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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


def is_repeating(schedule: Schedule) -> bool:
    return not isinstance(schedule, OnceSchedule | ManualSchedule)


# --- cron -------------------------------------------------------------------

_CRON_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("weekday", 0, 6),
)


def _cron_field(raw: str, name: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()
    for part in raw.split(","):
        step = 1
        if "/" in part:
            part, step_raw = part.split("/", 1)
            if not step_raw.isdigit() or int(step_raw) < 1:
                raise ValueError(f"cron {name}: bad step {step_raw!r}")
            step = int(step_raw)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise ValueError(f"cron {name}: bad range {part!r}")
            start, end = int(a), int(b)
        elif part.isdigit():
            start = int(part)
            end = high if step > 1 else start
        else:
            raise ValueError(f"cron {name}: {part!r} is not a number (names are not accepted)")
        if name == "weekday" and end == 7:
            # Cron's Sunday is 0; accept 7 as Sunday too, as most crons do.
            values.add(0)
            if start == 7:
                continue
            end = 6
        if not (low <= start <= high and low <= end <= high and start <= end):
            raise ValueError(f"cron {name}: {part!r} is outside {low}-{high}")
        values.update(range(start, end + 1, step))
    return frozenset(values)


class Cron(BaseModel):
    """A parsed cron expression: the allowed values of each field. ``weekday``
    is cron's (0 is Sunday)."""

    model_config = ConfigDict(frozen=True)

    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    weekday: frozenset[int]
    #: Whether day-of-month and day-of-week were both restricted: cron then runs
    #: on a day matching EITHER, not both.
    either_day: bool


def parse_cron(expr: str) -> Cron:
    """Parse ``expr`` or raise ``ValueError`` naming the field that is wrong."""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron needs five fields: minute hour day month weekday")
    fields = {
        name: _cron_field(raw, name, low, high)
        for raw, (name, low, high) in zip(parts, _CRON_FIELDS, strict=True)
    }
    return Cron(**fields, either_day=parts[2] != "*" and parts[4] != "*")


def _cron_day_ok(cron: Cron, wall: datetime) -> bool:
    weekday = (wall.weekday() + 1) % 7  # Python: Monday 0; cron: Sunday 0
    day_ok = wall.day in cron.day
    weekday_ok = weekday in cron.weekday
    if cron.either_day:
        return day_ok or weekday_ok
    return day_ok and weekday_ok


def _next_cron(cron: Cron, after: datetime) -> datetime | None:
    """The first wall-clock minute after ``after`` the expression names, within
    the next four years (a 29 February-only expression still has one)."""
    wall = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = wall + timedelta(days=366 * 4)
    while wall < limit:
        if wall.month not in cron.month:
            wall = (wall.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
            continue
        if not _cron_day_ok(cron, wall):
            wall = wall.replace(hour=0, minute=0) + timedelta(days=1)
            continue
        if wall.hour not in cron.hour:
            wall = wall.replace(minute=0) + timedelta(hours=1)
            continue
        if wall.minute not in cron.minute:
            wall += timedelta(minutes=1)
            continue
        return wall
    return None


# --- the one question -------------------------------------------------------


def _next_wall(schedule: Schedule, after: datetime) -> datetime | None:
    """The first wall-clock time ``schedule`` names strictly after ``after``
    (both naive local)."""
    if isinstance(schedule, HourlySchedule):
        slot = after.replace(minute=schedule.minute, second=0, microsecond=0)
        return slot if slot > after else slot + timedelta(hours=1)
    if isinstance(schedule, CronSchedule):
        return _next_cron(parse_cron(schedule.expr), after)
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


def next_slot(
    schedule: Schedule,
    after: datetime,
    *,
    to_local: ToLocal = _os_local,
    to_instant: ToInstant = _os_instant,
) -> datetime | None:
    """The first instant ``schedule`` names strictly after the instant ``after``;
    ``None`` when it names none (manual, or a one-off already behind)."""
    if isinstance(schedule, ManualSchedule):
        return None
    if isinstance(schedule, OnceSchedule):
        return schedule.at if schedule.at > after else None
    wall = _next_wall(schedule, to_local(after))
    while wall is not None:
        instant = to_instant(wall)
        # A wall time that does not exist (the hour summer time skips) reads
        # back as a later instant; one that exists twice reads as the first.
        # Either way the slot must still be after ``after``.
        if instant > after:
            return instant
        wall = _next_wall(schedule, wall)
    return None


def shortest_gap(
    schedule: Schedule,
    *,
    start: datetime,
    to_local: ToLocal = _os_local,
    to_instant: ToInstant = _os_instant,
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
