"""Schedules: their slots on the local wall clock, the cron parser, the limits
a task's config keeps, and each task's grace (spec channels "Keep scheduled
tasks as machine-local resources", "Run a scheduled task at the times it names",
"Catch up a missed run once, within its grace")."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from coffer.domain.channel.schedule import (
    MIN_REPEAT,
    CronSchedule,
    DailySchedule,
    HourlySchedule,
    ManualSchedule,
    OnceSchedule,
    WeekdaysSchedule,
    WeeklySchedule,
    is_repeating,
    next_slot,
    parse_cron,
    shortest_gap,
)
from coffer.domain.channel.scheduled_task import (
    ScheduledTaskConfig,
    TaskChat,
    grace_for,
    min_repeat_ok,
)


@pytest.fixture
def local_tz() -> Iterator[None]:
    """Run under a known zone with daylight saving (Europe/Berlin)."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Berlin"
    time.tzset()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def _local(*args: int) -> datetime:
    """An aware instant from local wall-clock fields."""
    return datetime(*args).astimezone()  # type: ignore[arg-type]


def _wall(moment: datetime | None) -> tuple[int, ...]:
    assert moment is not None
    local = moment.astimezone()
    return (local.year, local.month, local.day, local.hour, local.minute)


# --- next_slot ---------------------------------------------------------------


def test_once_has_one_slot_and_none_after_it(local_tz: None) -> None:
    at = _local(2026, 10, 30, 9, 0)
    schedule = OnceSchedule(at=at)
    assert next_slot(schedule, at - timedelta(hours=1)) == at
    assert next_slot(schedule, at) is None
    assert next_slot(schedule, at + timedelta(minutes=1)) is None


def test_once_refuses_a_time_without_an_offset() -> None:
    with pytest.raises(ValidationError):
        OnceSchedule(at=datetime(2026, 10, 30, 9, 0))


def test_hourly_daily_and_weekly_slots(local_tz: None) -> None:
    # Thursday 2026-10-29 10:20 local.
    after = _local(2026, 10, 29, 10, 20)
    assert _wall(next_slot(HourlySchedule(minute=15), after)) == (2026, 10, 29, 11, 15)
    assert _wall(next_slot(HourlySchedule(minute=45), after)) == (2026, 10, 29, 10, 45)
    assert _wall(next_slot(DailySchedule(time="09:00"), after)) == (2026, 10, 30, 9, 0)
    assert _wall(next_slot(DailySchedule(time="18:00"), after)) == (2026, 10, 29, 18, 0)
    # weekday 0 = Monday.
    assert _wall(next_slot(WeeklySchedule(weekday=0, time="09:00"), after)) == (
        2026,
        11,
        2,
        9,
        0,
    )


def test_weekdays_skip_the_weekend(local_tz: None) -> None:
    friday_evening = _local(2026, 10, 30, 19, 0)
    assert _wall(next_slot(WeekdaysSchedule(time="09:00"), friday_evening)) == (
        2026,
        11,
        2,
        9,
        0,
    )


def test_a_daily_slot_keeps_its_wall_time_across_daylight_saving(local_tz: None) -> None:
    # Berlin leaves summer time on 2026-10-25 at 03:00.
    before = _local(2026, 10, 24, 9, 30)
    first = next_slot(DailySchedule(time="09:00"), before)
    second = next_slot(DailySchedule(time="09:00"), first)  # type: ignore[arg-type]
    assert _wall(first) == (2026, 10, 25, 9, 0)
    assert _wall(second) == (2026, 10, 26, 9, 0)
    # The wall clock is the same; the instants are 25 hours apart.
    assert second - first == timedelta(hours=24)  # type: ignore[operator]
    assert first.utcoffset() != datetime(2026, 10, 24, 12, tzinfo=UTC).astimezone().utcoffset()  # type: ignore[union-attr]


def test_manual_never_has_a_slot() -> None:
    assert next_slot(ManualSchedule(), datetime.now(tz=UTC)) is None
    assert not is_repeating(ManualSchedule())
    assert not is_repeating(OnceSchedule(at=datetime.now(tz=UTC)))
    assert is_repeating(DailySchedule(time="09:00"))


# --- cron ------------------------------------------------------------------


def test_cron_fields_lists_ranges_and_steps() -> None:
    cron = parse_cron("0,30 9-17/2 * * 1-5")
    assert cron.minute == frozenset({0, 30})
    assert cron.hour == frozenset({9, 11, 13, 15, 17})
    # cron weekday 1-5 = Monday..Friday.
    assert len(cron.weekday) == 5


def test_cron_accepts_seven_as_sunday() -> None:
    assert parse_cron("0 9 * * 7").weekday == parse_cron("0 9 * * 0").weekday


@pytest.mark.parametrize(
    "expr", ["", "* * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "*/0 * * * *", "a * * * *"]
)
def test_cron_refuses_a_malformed_expression(expr: str) -> None:
    with pytest.raises(ValueError):
        parse_cron(expr)


def test_cron_slots_follow_the_expression(local_tz: None) -> None:
    after = _local(2026, 10, 29, 10, 20)  # Thursday
    assert _wall(next_slot(CronSchedule(expr="0 9 * * 1"), after)) == (2026, 11, 2, 9, 0)
    assert _wall(next_slot(CronSchedule(expr="30 10 * * *"), after)) == (2026, 10, 29, 10, 30)


def test_cron_day_of_month_or_weekday_either_matches(local_tz: None) -> None:
    # Both restricted: either may match, as in classic cron. The 1st of
    # November 2026 is a Sunday; Monday the 2nd also matches by weekday.
    after = _local(2026, 10, 31, 12, 0)
    first = next_slot(CronSchedule(expr="0 9 1 * 1"), after)
    assert _wall(first) == (2026, 11, 1, 9, 0)
    assert _wall(next_slot(CronSchedule(expr="0 9 1 * 1"), first)) == (2026, 11, 2, 9, 0)  # type: ignore[arg-type]


# --- limits ----------------------------------------------------------------


def test_shortest_gap_measures_the_tightest_repeat(local_tz: None) -> None:
    start = _local(2026, 10, 29, 0, 0)
    assert shortest_gap(CronSchedule(expr="*/5 * * * *"), start=start) == timedelta(minutes=5)
    assert shortest_gap(HourlySchedule(minute=0), start=start) == timedelta(hours=1)
    assert not min_repeat_ok(CronSchedule(expr="*/5 * * * *"), timedelta(minutes=5))
    assert min_repeat_ok(CronSchedule(expr="*/15 * * * *"), MIN_REPEAT)


def _config(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schedule": {"kind": "daily", "time": "09:00"},
        "prompt": "Check the deploy",
        "chat": {"channel": "ch-1", "chat_id": "owner"},
    }
    return {**base, **changes}


def test_a_fresh_task_may_name_agent_model_and_directory() -> None:
    config = ScheduledTaskConfig.model_validate(
        _config(session="fresh", agent="codex", model="gpt-5", cwd="/tmp/work")
    )
    assert config.agent == "codex" and config.model == "gpt-5"


@pytest.mark.parametrize(
    "changes",
    [
        {"session": "continue", "agent": "codex"},  # continue names no agent
        {"session": "fresh", "model": "gpt-5"},  # a model needs its agent
        {"origin": "agent"},  # an agent books one-offs only
        {"prompt": ""},
        {"prompt": "x" * 8001},
    ],
)
def test_a_config_breaking_a_rule_is_refused(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScheduledTaskConfig.model_validate(_config(**changes))


def test_the_chat_defaults_to_a_direct_chat_with_no_thread() -> None:
    chat = TaskChat(channel="ch", chat_id="c")
    assert (chat.chat_kind, chat.thread_id, chat.conversation_thread_id) == ("direct", "", "")


# --- grace -------------------------------------------------------------------


def _once(at: datetime) -> ScheduledTaskConfig:
    return ScheduledTaskConfig.model_validate(
        _config(schedule={"kind": "once", "at": at.isoformat()})
    )


@pytest.mark.parametrize(
    ("waited", "grace"),
    [
        (timedelta(minutes=10), timedelta(minutes=15)),  # floor
        (timedelta(hours=1), timedelta(minutes=30)),  # half
        (timedelta(days=1), timedelta(hours=2)),  # ceiling
    ],
)
def test_a_one_off_grace_is_half_its_wait_clamped(waited: timedelta, grace: timedelta) -> None:
    slot = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
    assert grace_for(_once(slot), slot=slot, created_at=slot - waited) == grace


def test_a_repeating_slot_lasts_until_the_end_of_its_day(local_tz: None) -> None:
    slot = _local(2026, 10, 29, 9, 0)
    config = ScheduledTaskConfig.model_validate(_config())
    assert grace_for(config, slot=slot, created_at=slot - timedelta(days=3)) == timedelta(hours=15)
