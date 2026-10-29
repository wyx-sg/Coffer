"""Scheduled tasks end to end through the real channel core (spec channels "Keep
scheduled tasks as machine-local resources", "Run a scheduled task at the times
it names", "Catch up a missed run once, within its grace", "Run a scheduled task
in the chat it names", "Stay silent when a scheduled run has nothing to say",
"Keep every scheduled run in the task's history").

The clock is the test's: a pass is run by hand with the clock where the test
put it, and the turn it starts is a real turn through the turn driver."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import timedelta

import pytest

from coffer.application.channel import turn_origin
from coffer.application.channel.schedule.kind import KIND
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import StorageClass
from coffer.domain.turn_markers import SCHEDULED
from coffer.surfaces.http.schedule_wiring import ScheduleWiring

from .conftest import ChannelEnv, default_reply_adapter, inbound, wait_until
from .scheduling import START, build_scheduling, daily, task_config
from .test_queue_and_stop import GatedAdapter


@pytest.fixture(autouse=True)
def _utc() -> Iterator[None]:
    """Local time is UTC here, so a daily 10:30 is 10:30 on the test clock."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    yield
    turn_origin.clear()
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


# --- the resource ------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a task in a paired chat is created")
async def test_a_task_in_a_paired_chat_is_created(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    task = await s.tasks.create(
        None,
        task_config(channel, schedule={"kind": "weekdays", "time": "09:00"}),
        actor="test",
    )
    assert task.kind == KIND
    assert env.resources.storage_of(KIND, task.config) is StorageClass.LOCAL
    assert task.name == "Summarise the open pull requests"
    view = await s.tasks.view(task.uid)
    # Thursday 10:00 → Friday 09:00.
    assert view.next_run == (START + timedelta(days=1)).replace(hour=9)
    # The generic create checks the same: the kind holds the rule.
    with pytest.raises(ConfigValidationError, match="not paired"):
        await env.resources.register(KIND, "x", task_config(channel, "stranger"), "test")


@pytest.mark.acceptance(
    spec="channels", scenario="a task in a chat the channel never paired is refused"
)
async def test_a_task_in_an_unpaired_chat_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    with pytest.raises(ConfigValidationError, match="not paired"):
        await s.tasks.create(None, task_config(channel, "stranger"), actor="test")
    assert await env.resources.list(kind=KIND) == []


@pytest.mark.acceptance(spec="channels", scenario="a schedule closer than 15 minutes is refused")
async def test_a_schedule_closer_than_fifteen_minutes_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    with pytest.raises(ConfigValidationError, match="15 minutes"):
        await s.tasks.create(
            None,
            task_config(channel, schedule={"kind": "cron", "expr": "*/5 * * * *"}),
            actor="test",
        )
    past = (START - timedelta(minutes=1)).isoformat()
    with pytest.raises(ConfigValidationError):
        await s.tasks.create(
            None, task_config(channel, schedule={"kind": "once", "at": past}), actor="test"
        )


async def test_removing_a_channel_removes_its_tasks(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    await s.tasks.create(None, task_config(channel), actor="test")
    wiring = ScheduleWiring(
        tasks=s.tasks, scheduler=s.scheduler, runs=s.runs, resources=env.resources
    )
    await wiring.forget_channel(channel.uid)
    assert await env.resources.list(kind=KIND) == []


# --- running on time ---------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a daily task runs at its time")
async def test_a_daily_task_runs_at_its_time(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, adapter = await env.paired_channel()
    env.provider.adapter = default_reply_adapter("Two PRs are open.")
    task = await s.tasks.create(None, task_config(channel, schedule=daily("10:30")), actor="t")

    await s.tick()  # 10:00: not yet
    assert await s.history(task.uid) == []

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "replied" and run.trigger == "schedule" and not run.catch_up
    assert run.due_at == START.replace(minute=30)
    await wait_until(lambda: "Two PRs are open." in adapter.texts())
    prompt = env.raw_prompts(run.conversation_id)[0]
    assert prompt.startswith(f"[{SCHEDULED}]")
    assert "Summarise the open pull requests" in prompt

    view = await s.tasks.view(task.uid)
    assert view.next_run == START.replace(minute=30) + timedelta(days=1)
    await s.tick()  # the same slot never runs twice
    assert len(await s.history(task.uid)) == 1


@pytest.mark.acceptance(
    spec="channels", scenario="a slot whose previous run is still going is skipped"
)
async def test_a_slot_whose_previous_run_is_still_going_is_skipped(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    gated = GatedAdapter()
    env.provider.adapter = gated
    task = await s.tasks.create(
        None, task_config(channel, schedule={"kind": "hourly", "minute": 0}), actor="t"
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
    channel, _ = await env.paired_channel()
    task = await s.tasks.create(None, task_config(channel, schedule=daily("10:30")), actor="t")
    s.clock.advance(timedelta(hours=3))  # asleep until 13:00
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.catch_up and run.outcome == "replied"
    prompt = env.raw_prompts(run.conversation_id)[0]
    assert "running now at 2026-10-29 13:00" in prompt and "late" in prompt
    assert "due: 2026-10-29 10:30" in prompt


@pytest.mark.acceptance(spec="channels", scenario="a week of missed daily slots runs once")
async def test_a_week_of_missed_slots_runs_once(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    task = await s.tasks.create(None, task_config(channel, schedule=daily("10:30")), actor="t")
    s.clock.advance(timedelta(days=7, hours=1))  # a week later, 11:00
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.due_at == START.replace(minute=30) + timedelta(days=7)
    await s.tick()
    assert len(await s.history(task.uid)) == 1


@pytest.mark.acceptance(spec="channels", scenario="a follow-up missed past its grace is skipped")
async def test_a_follow_up_missed_past_its_grace_is_skipped(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, adapter = await env.paired_channel()
    args = s.in_turn("conv-1", channel)
    booked = await s.tools.schedule({**args, "after": "30m", "prompt": "check the deploy"})
    s.clock.advance(timedelta(hours=1))  # off from 10:00 to 11:00; grace 15 min
    await s.tick()
    (run,) = await s.history(booked["id"])
    assert run.outcome == "skipped" and "missed" in run.reason
    assert adapter.texts() == []
    # A one-off the agent booked is over once its slot is: it is removed.
    assert await env.resources.list(kind=KIND) == []


async def test_a_task_that_does_not_catch_up_skips_a_late_slot(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    task = await s.tasks.create(
        None, task_config(channel, schedule=daily("10:30"), catch_up=False), actor="t"
    )
    s.clock.advance(timedelta(hours=1))
    await s.tick()
    (run,) = await s.history(task.uid)
    assert run.outcome == "skipped"


# --- the chat -------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="a fresh task opens a new conversation on its own agent"
)
async def test_a_fresh_task_opens_a_new_conversation(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    other = env.add_agent("codex", reply="from codex")
    channel, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    before = await env.active_conversation(channel)
    task = await s.tasks.create(
        None,
        task_config(channel, session="fresh", agent="codex", cwd="/tmp"),
        actor="t",
    )
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "replied"
    await wait_until(lambda: "from codex" in adapter.texts())
    assert other.turns and other.turns[0][0] == run.conversation_id
    conversation = await env.chat.get_conversation(run.conversation_id)
    assert conversation.agent_key == "codex"
    assert conversation.agent_config.cwd == "/tmp"
    assert await env.active_conversation(channel) == run.conversation_id != before


@pytest.mark.acceptance(spec="channels", scenario="a follow-up with nothing new says nothing")
async def test_a_silent_reply_is_not_sent(env: ChannelEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, adapter = await env.paired_channel()
    env.provider.adapter = default_reply_adapter("[SILENT] still deploying")
    task = await s.tasks.create(None, task_config(channel), actor="t")
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "silent"
    assert not any("still deploying" in t for t in adapter.texts())
    # A person's message is answered whatever the reply starts with.
    await env.processor.on_message(inbound("tg", "owner", "hi"))
    await wait_until(lambda: any("still deploying" in t for t in adapter.texts()))


@pytest.mark.acceptance(spec="channels", scenario="a repeating task that keeps failing is paused")
async def test_a_repeating_task_that_keeps_failing_is_paused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    await env.pair(channel, "second")
    task = await s.tasks.create(None, task_config(channel, "second"), actor="t")
    await env.peers.delete_by_chat(channel.uid, "second")
    s.clock.advance(timedelta(minutes=30))  # 10:30, then the next two days
    for _ in range(3):
        await s.tick()
        s.clock.advance(timedelta(days=1))
    rows = await s.history(task.uid)
    assert [r.outcome for r in rows] == ["failed"] * 3
    assert "no longer paired" in rows[0].reason
    assert not (await env.resources.get(task.uid)).enabled
    assert s.notices and "paused" in s.notices[0][1]


# --- history -------------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a run's history row says how it ended")
async def test_the_history_says_how_each_run_ended(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    task = await s.tasks.create(
        None, task_config(channel, schedule=daily("10:30"), catch_up=False), actor="t"
    )
    s.clock.advance(timedelta(hours=1))  # missed, no catch-up
    await s.tick()
    s.clock.advance(timedelta(days=1, minutes=-30))  # tomorrow 10:30, on time
    await s.tick()
    rows = await s.settled(task.uid, count=2)
    assert [r.outcome for r in rows] == ["replied", "skipped"]
    assert rows[0].conversation_id and rows[1].reason


@pytest.mark.acceptance(
    spec="channels", scenario="a run interrupted by a stop is closed on the next start"
)
async def test_a_run_left_open_is_closed_on_start(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    gated = GatedAdapter()
    env.provider.adapter = gated
    task = await s.tasks.create(None, task_config(channel), actor="t")
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
    channel, adapter = await env.paired_channel()
    env.provider.adapter = default_reply_adapter("ran by hand")
    task = await s.tasks.create(
        None,
        task_config(channel, schedule={"kind": "weekly", "weekday": 0, "time": "09:00"}),
        actor="t",
    )
    await env.resources.set_enabled(task.uid, False, "t")
    task = await env.resources.get(task.uid)
    await s.scheduler.run_now(task)
    (run,) = await s.settled(task.uid)
    assert run.trigger == "manual" and run.outcome == "replied"
    await wait_until(lambda: "ran by hand" in adapter.texts())
    assert "started by hand" in env.raw_prompts(run.conversation_id)[0]
    assert not (await env.resources.get(task.uid)).enabled
