"""Five-field cron expressions, read on a wall clock (spec channels "Run a
scheduled task at the times it names"): the parser and the one question asked
of a parsed expression, its next minute after a wall time."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

__all__ = ["Cron", "next_cron", "parse_cron"]

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


def next_cron(cron: Cron, after: datetime) -> datetime | None:
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
