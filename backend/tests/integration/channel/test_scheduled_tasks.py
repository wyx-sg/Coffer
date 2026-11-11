"""Scheduled tasks end to end through the real chat platform (spec channels
"Keep scheduled tasks as machine-local resources", "Run a scheduled task at the
times it names", "Catch up a missed run once, within its grace", "Run a
scheduled task in a fresh conversation of its own", "Keep every scheduled run
in the task's history").

The clock is the test's: a pass is run by hand with the clock where the test
put it, and the turn it starts is a real turn through the orchestrator."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, ConfigDict

from coffer.application.channel.schedule.kind import KIND
from coffer.domain.chat.events import TurnError, TurnStarted
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, StorageClass
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.surfaces.http.schedule_wiring import _Reads
from tests.unit.chat.conftest import FakeAgentAdapter

from .conftest import ChannelEnv, default_reply_adapter
from .scheduling import START, build_scheduling, daily, task_config
from .test_queue_and_stop import GatedAdapter


class _AnyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")


@pytest.fixture(autouse=True)
def _utc() -> Iterator[None]:
    """Local time is UTC here, so a daily 10:30 is 10:30 on the test clock."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    yield
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


# --- the resource ------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a task is created")
async def test_a_task_is_created(env: ChannelEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    s = build_scheduling(env, monkeypatch)
    env.add_agent("codex")
    task = await s.tasks.create(
        None,
        task_config(
            agent="codex",
            cwd="/tmp/site",
            schedule={"kind": "daily", "time": "11:00", "timezone": "Asia/Singapore"},
        ),
        actor="test",
    )
    assert task.kind == KIND
    assert env.resources.storage_of(KIND, task.config) is StorageClass.LOCAL
    assert task.name == "Summarise the open pull requests"
    assert task.config["agent"] == "codex" and task.config["cwd"] == "/tmp/site"
    assert "chat" not in task.config
    view = await s.tasks.view(task.uid)
    # Thursday 10:00 UTC is 18:00 in Singapore: the next 11:00 there is
    # Friday's, 03:00 UTC.
    assert view.next_run == datetime(2026, 10, 30, 3, 0, tzinfo=UTC)


@pytest.mark.acceptance(spec="channels", scenario="a task without an agent is refused")
async def test_a_task_without_an_agent_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    config = task_config()
    config.pop("agent")
    with pytest.raises(ConfigValidationError, match="agent"):
        await s.tasks.create(None, config, actor="test")
    # A chat is no part of a task now.
    with pytest.raises(ConfigValidationError, match="chat"):
        await s.tasks.create(
            None, task_config(chat={"channel": "c", "chat_id": "owner"}), actor="test"
        )
    # The generic create holds the same rules.
    with pytest.raises(ConfigValidationError):
        await env.resources.register(KIND, "x", config, "test")
    assert await env.resources.list(kind=KIND) == []


@pytest.mark.acceptance(spec="channels", scenario="a schedule closer than 15 minutes is refused")
async def test_a_schedule_closer_than_fifteen_minutes_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    with pytest.raises(ConfigValidationError, match="15 minutes"):
        await s.tasks.create(
            None, task_config(schedule={"kind": "cron", "expr": "*/5 * * * *"}), actor="test"
        )
    past = (START - timedelta(minutes=1)).isoformat()
    with pytest.raises(ConfigValidationError):
        await s.tasks.create(None, task_config(schedule={"kind": "once", "at": past}), actor="test")
    # Monday to Friday is a cron expression now; the shape is gone.
    with pytest.raises(ConfigValidationError):
        await s.tasks.create(
            None, task_config(schedule={"kind": "weekdays", "time": "09:00"}), actor="test"
        )


@pytest.mark.acceptance(spec="channels", scenario="an unknown timezone is refused")
async def test_an_unknown_timezone_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    with pytest.raises(ConfigValidationError, match="Mars/Olympus"):
        await s.tasks.create(
            None,
            task_config(schedule={"kind": "daily", "time": "09:00", "timezone": "Mars/Olympus"}),
            actor="test",
        )
    assert await env.resources.list(kind=KIND) == []


@pytest.mark.acceptance(
    spec="channels", scenario="a task an older Coffer wrote is read without its chat"
)
async def test_a_task_an_older_coffer_wrote_is_read_without_its_chat(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    # Files as the 2026-10-29 build wrote them, stored as they are.
    env.kinds[KIND] = Kind(
        name=KIND,
        display_name="Scheduled task",
        config_schema=_AnyConfig,
        free_name=True,
        storage=StorageClass.LOCAL,
    )
    chat = {"channel": "c1", "chat_id": "owner", "chat_kind": "direct"}
    old = await env.resources.register(
        KIND,
        "Standup",
        {
            "schedule": {"kind": "weekdays", "time": "09:00"},
            "prompt": "Post the standup",
            "chat": chat,
            "session": "fresh",
            "material": "none",
            "template": "",
            "origin": "owner",
            "chain_index": 1,
            "catch_up": True,
        },
        "test",
    )
    follow_up = await env.resources.register(
        KIND,
        "Check the deploy",
        {
            "schedule": {"kind": "once", "at": (START + timedelta(hours=1)).isoformat()},
            "prompt": "Check the deploy",
            "chat": chat,
            "session": "continue",
            "origin": "agent",
        },
        "test",
    )
    s = build_scheduling(env, monkeypatch, s.clock)

    assert await s.tasks.drop_retired_follow_ups() == 1
    (view,) = await s.tasks.views()
    assert view.task.uid == old.uid != follow_up.uid
    assert view.config.agent == "claude_code"
    assert view.config.schedule.kind == "cron"
    assert view.config.schedule.expr == "0 9 * * 1-5"  # type: ignore[union-attr]
    assert "chat" not in view.config.model_dump()


# --- running on time ---------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a daily task runs at its time")
async def test_a_daily_task_runs_at_its_time(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("Two PRs are open.")
    task = await s.tasks.create(None, task_config(schedule=daily("10:30")), actor="t")

    await s.tick()  # 10:00: not yet
    assert await s.history(task.uid) == []

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "done" and run.trigger == "schedule" and not run.catch_up
    assert run.due_at == START.replace(minute=30)
    assert env.raw_prompts(run.conversation_id) == ["Summarise the open pull requests"]

    view = await s.tasks.view(task.uid)
    assert view.next_run == START.replace(minute=30) + timedelta(days=1)
    await s.tick()  # the same slot never runs twice
    assert len(await s.history(task.uid)) == 1


@pytest.mark.acceptance(spec="channels", scenario="a one-off task is switched off after it runs")
async def test_a_one_off_task_is_switched_off_after_it_runs(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    at = (START + timedelta(minutes=30)).isoformat()
    task = await s.tasks.create(None, task_config(schedule={"kind": "once", "at": at}), actor="t")
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "done"
    assert not (await env.resources.get(task.uid)).enabled


@pytest.mark.acceptance(
    spec="channels", scenario="a slot whose previous run is still going is skipped"
)
async def test_a_slot_whose_previous_run_is_still_going_is_skipped(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    gated = GatedAdapter()
    env.provider.adapter = gated
    task = await s.tasks.create(
        None, task_config(schedule={"kind": "hourly", "minute": 0}), actor="t"
    )
    s.clock.advance(timedelta(hours=1))  # 11:00
    await s.tick()
    await gated.entered.wait()
    s.clock.advance(timedelta(hours=1))  # 12:00, the 11:00 run still going
    await s.tick()
    rows = await s.history(task.uid)
    assert [r.outcome for r in rows] == ["skipped", "running"]
    assert rows[0].reason == "the previous run was still going"
    gated.release.set()
    await s.settled(task.uid, count=2)
    assert not s.scheduler.is_running(task.uid)


# --- catching up ---------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="a daily task missed this morning runs late, once"
)
async def test_a_missed_daily_slot_runs_late_once(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.tasks.create(None, task_config(schedule=daily("10:30")), actor="t")
    s.clock.advance(timedelta(hours=3))  # asleep until 13:00
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.catch_up and run.outcome == "done"
    (prompt,) = env.raw_prompts(run.conversation_id)
    assert prompt.startswith("Summarise the open pull requests\n\n")
    assert "due at 2026-10-29 10:30" in prompt and "late, at 2026-10-29 13:00" in prompt


@pytest.mark.acceptance(spec="channels", scenario="a week of missed daily slots runs once")
async def test_a_week_of_missed_slots_runs_once(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.tasks.create(None, task_config(schedule=daily("10:30")), actor="t")
    s.clock.advance(timedelta(days=7, hours=1))  # a week later, 11:00
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.due_at == START.replace(minute=30) + timedelta(days=7)
    await s.tick()
    assert len(await s.history(task.uid)) == 1


@pytest.mark.acceptance(spec="channels", scenario="a one-off missed past its grace is skipped")
async def test_a_one_off_missed_past_its_grace_is_skipped(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    at = (START + timedelta(minutes=30)).isoformat()
    task = await s.tasks.create(None, task_config(schedule={"kind": "once", "at": at}), actor="t")
    s.clock.advance(timedelta(hours=1))  # off from 10:00 to 11:00; grace 15 min
    await s.tick()
    (run,) = await s.history(task.uid)
    assert run.outcome == "skipped" and "missed" in run.reason
    assert not (await env.resources.get(task.uid)).enabled


async def test_a_task_that_does_not_catch_up_skips_a_late_slot(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.tasks.create(
        None, task_config(schedule=daily("10:30"), catch_up=False), actor="t"
    )
    s.clock.advance(timedelta(hours=1))
    await s.tick()
    (run,) = await s.history(task.uid)
    assert run.outcome == "skipped"


# --- the conversation ------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="a task runs in a new conversation of its own each time"
)
async def test_a_task_runs_in_a_new_conversation_each_time(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, adapter = await env.paired_channel()
    env.provider.adapter = default_reply_adapter("The build is green.")
    task = await s.tasks.create(
        "Nightly build", task_config(cwd="/tmp/site", schedule=daily("10:30")), actor="t"
    )

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (first,) = await s.settled(task.uid)
    s.clock.advance(timedelta(days=1))
    await s.tick()
    second, again = await s.settled(task.uid, count=2)
    assert again == first

    for run in (first, second):
        assert run.outcome == "done" and run.reason == ""
        conversation = await env.chat.get_conversation(run.conversation_id)
        assert conversation.agent_key == "builtin"
        assert conversation.agent_config.cwd == "/tmp/site"
        assert conversation.channel_uid is None
        assert conversation.title == "Nightly build"
        assert env.raw_prompts(run.conversation_id) == ["Summarise the open pull requests"]
    assert first.conversation_id != second.conversation_id
    # Nothing was posted to any chat, and the chat's own conversation is untouched.
    assert adapter.texts() == []
    assert await env.active_conversation(channel) is None


@pytest.mark.acceptance(
    spec="channels", scenario="a task that names no directory runs in Coffer's workspace"
)
async def test_a_task_without_a_directory_runs_in_the_coffer_workspace(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("Done.")
    task = await s.tasks.create("Tidy", task_config(schedule=daily("10:30")), actor="t")

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)

    conversation = await env.chat.get_conversation(run.conversation_id)
    assert conversation.agent_config.cwd == default_workspace_dir()
    assert conversation.agent_config.cwd.endswith("/.coffer/content/workspace")


@pytest.mark.acceptance(spec="channels", scenario="a task whose turn fails is recorded failed")
async def test_a_task_whose_turn_fails_is_recorded_failed(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    _, adapter = await env.paired_channel()
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    task = await s.tasks.create(None, task_config(), actor="t")
    run = await s.scheduler.run_now(await env.resources.get(task.uid))
    (ended,) = await s.settled(task.uid)
    assert ended.run_id == run.run_id
    assert ended.outcome == "failed" and ended.reason == "upstream timed out"
    assert adapter.texts() == []


@pytest.mark.acceptance(spec="channels", scenario="a repeating task that keeps failing is paused")
async def test_a_repeating_task_that_keeps_failing_is_paused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    task = await s.tasks.create(None, task_config(schedule=daily("10:30")), actor="t")
    for day in range(3):
        s.clock.now = START.replace(minute=30) + timedelta(days=day)
        await s.tick()
        await s.settled(task.uid, count=day + 1)
    rows = await s.history(task.uid)
    assert [r.outcome for r in rows] == ["failed"] * 3
    assert not (await env.resources.get(task.uid)).enabled


# --- history -------------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a run's history row says how it ended")
async def test_the_history_says_how_each_run_ended(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.tasks.create(
        None, task_config(schedule=daily("10:30"), catch_up=False), actor="t"
    )
    s.clock.advance(timedelta(hours=1))  # missed, no catch-up
    await s.tick()
    s.clock.advance(timedelta(days=1, minutes=-30))  # tomorrow 10:30, on time
    await s.tick()
    rows = await s.settled(task.uid, count=2)
    assert [r.outcome for r in rows] == ["done", "skipped"]
    assert rows[0].conversation_id and rows[1].reason


@pytest.mark.acceptance(spec="channels", scenario="a run's conversation opens from its history")
async def test_the_history_names_each_run_s_conversation(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.tasks.create(None, task_config(), actor="t")
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (row,) = await s.settled(task.uid)
    reads = _Reads(s.runs, env.chat)
    found = await reads.conversations({row.conversation_id, ""})
    conv = found[row.conversation_id]
    assert conv["conversation_id"] == row.conversation_id
    assert conv["agent_key"] and "session_id" in conv and conv["running"] is False
    # A conversation removed since is left out; the row keeps its id.
    await env.chat.remove_conversation(row.conversation_id)
    assert await reads.conversations({row.conversation_id}) == {}


@pytest.mark.acceptance(
    spec="channels", scenario="a run interrupted by a stop is closed on the next start"
)
async def test_a_run_left_open_is_closed_on_start(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    gated = GatedAdapter()
    env.provider.adapter = gated
    task = await s.tasks.create(None, task_config(), actor="t")
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    await gated.entered.wait()
    # A daemon that starts again finds the row still open.
    closed = await s.runs.close_interrupted(
        reason="Coffer stopped while it was running", finished_at=s.clock()
    )
    assert closed == 1
    (row,) = await s.history(task.uid)
    assert row.outcome == "failed" and "stopped" in row.reason
    gated.release.set()


@pytest.mark.acceptance(spec="channels", scenario="the owner runs a task now from the page")
async def test_run_now_runs_a_paused_task_once(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("ran by hand")
    task = await s.tasks.create(
        None,
        task_config(schedule={"kind": "weekly", "weekday": 0, "time": "09:00"}),
        actor="t",
    )
    await env.resources.set_enabled(task.uid, False, "t")
    task = await env.resources.get(task.uid)
    await s.scheduler.run_now(task)
    (run,) = await s.settled(task.uid)
    assert run.trigger == "manual" and run.outcome == "done"
    # A run by hand is the prompt alone: it is not late for anything.
    assert env.raw_prompts(run.conversation_id) == ["Summarise the open pull requests"]
    assert not (await env.resources.get(task.uid)).enabled


# --- the experimental feature ---------------------------------------------------


@pytest.mark.acceptance(spec="experimental-features", scenario="scheduled tasks off runs nothing")
async def test_scheduled_tasks_off_runs_nothing(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    switch = {"on": False}
    s.scheduler._enabled = lambda: switch["on"]
    task = await s.tasks.create(None, task_config(), actor="t")
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    assert await s.history(task.uid) == []
    # Switched on: the slot that just passed runs, late, within its grace.
    switch["on"] = True
    await s.tick()
    (row,) = await s.settled(task.uid)
    assert row.outcome == "done"
