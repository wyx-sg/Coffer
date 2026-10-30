"""Follow-ups an agent books, the daily report and `/status` (spec channels "Let
an agent book a follow-up in the thread it is answering", "Run a scheduled task
in the chat it names", "Write the daily report from the day's channel
conversations", "Skip the daily report on a day with no conversations", "List
and cancel a chat's scheduled tasks from /status")."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterator
from datetime import timedelta

import pytest

from coffer.application.channel import turn_origin
from coffer.application.channel.schedule.kind import KIND
from coffer.application.channel.status_tasks import TASK_CANCEL_KIND
from coffer.domain.turn_markers import MATERIAL

from .conftest import (
    ChannelEnv,
    FakeChannelAdapter,
    default_reply_adapter,
    inbound,
    tap_event,
    wait_until,
)
from .scheduling import START, build_scheduling
from .test_queue_and_stop import GatedAdapter

_MENTION = "<@{user_id}>"


@pytest.fixture(autouse=True)
def _utc() -> Iterator[None]:
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


# --- the tools -----------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="an agent books a follow-up in its thread")
async def test_an_agent_books_a_follow_up_in_its_thread(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    await env.pair(channel, "grp")
    args = s.in_turn("conv-1", channel, "grp", chat_kind="group", thread_id="th-1", asker="u-7")
    # Whatever the agent passes, the chat comes from the turn.
    answer = await s.tools.schedule(
        {**args, "after": "30m", "prompt": "Check the deploy", "chat_id": "elsewhere"}
    )
    task = await env.resources.get(answer["id"])
    chat = task.config["chat"]
    assert (chat["channel"], chat["chat_id"], chat["chat_kind"], chat["thread_id"]) == (
        channel.uid,
        "grp",
        "group",
        "th-1",
    )
    assert task.config["origin"] == "agent" and task.config["session"] == "continue"
    assert task.config["mention"]["user_id"] == "u-7"
    assert answer["next_run"].startswith("2026-10-29 10:30")
    listed = await s.tools.list_here(args)
    assert [t["id"] for t in listed["tasks"]] == [answer["id"]]


async def test_the_origin_is_known_only_while_the_turn_runs(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    gated = GatedAdapter()
    env.provider.adapter = gated
    await env.processor.on_message(inbound("tg", "owner", "deploy it"))
    await gated.entered.wait()
    conversation_id = await env.active_conversation(channel)
    assert conversation_id is not None
    origin = turn_origin.origin_of(conversation_id)
    assert origin is not None
    assert (origin.channel_uid, origin.chat_id, origin.asker_is_owner) == (
        channel.uid,
        "owner",
        True,
    )
    gated.release.set()
    await wait_until(lambda: turn_origin.origin_of(conversation_id) is None)


@pytest.mark.acceptance(spec="channels", scenario="a fourth follow-up in one thread is refused")
async def test_a_fourth_follow_up_in_one_thread_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    args = s.in_turn("conv-1", channel)
    for n in range(3):
        await s.tools.schedule({**args, "after": f"{n + 1}h", "prompt": f"check {n}"})
    with pytest.raises(ValueError, match="cancel one first"):
        await s.tools.schedule({**args, "after": "4h", "prompt": "one more"})
    for too_soon_or_late in ("1m", "8d"):
        with pytest.raises(ValueError):
            await s.tools.schedule({**args, "after": too_soon_or_late, "prompt": "x"})


@pytest.mark.acceptance(spec="channels", scenario="someone who may only ask cannot schedule")
async def test_someone_who_may_only_ask_cannot_schedule(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    args = s.in_turn("conv-1", channel, "grp", chat_kind="group", owner=False)
    with pytest.raises(ValueError, match="owners"):
        await s.tools.schedule({**args, "after": "1h", "prompt": "check"})
    with pytest.raises(ValueError, match="owners"):
        await s.tools.cancel({**args, "id": "anything"})
    assert await env.resources.list(kind=KIND) == []


async def test_a_run_of_a_repeating_task_schedules_nothing(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    args = s.in_turn("conv-1", channel, task_uid="t-1", task_repeats=True)
    with pytest.raises(ValueError, match="repeating"):
        await s.tools.schedule({**args, "after": "1h", "prompt": "check"})


@pytest.mark.acceptance(spec="channels", scenario="the tools work only inside a channel turn")
async def test_the_tools_work_only_inside_a_channel_turn(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    with pytest.raises(ValueError, match="only inside a channel turn"):
        await s.tools.schedule({"after": "1h", "prompt": "check"})
    with pytest.raises(ValueError, match="only inside a channel turn"):
        await s.tools.list_here({"_coffer_turn": "unknown"})


async def test_an_owner_s_recurring_task_is_set_up_from_chat(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    args = s.in_turn("conv-1", channel)
    answer = await s.tools.schedule(
        {
            **args,
            "prompt": "Morning summary",
            "repeat": {"kind": "weekdays", "time": "09:00"},
            "fresh": True,
        }
    )
    task = await env.resources.get(answer["id"])
    assert task.config["origin"] == "owner" and task.config["session"] == "fresh"
    assert answer["runs"] == "Monday to Friday at 09:00"
    with pytest.raises(ValueError, match="not a schedule"):
        await s.tools.schedule({**args, "prompt": "x", "repeat": {"kind": "fortnightly"}})


# --- a follow-up's run -------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a one-off follow-up is removed after it runs")
async def test_a_follow_up_is_removed_after_it_runs(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    args = s.in_turn("conv-1", channel)
    booked = await s.tools.schedule({**args, "after": "30m", "prompt": "check the deploy"})
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(booked["id"])
    assert run.outcome == "replied"

    async def gone() -> bool:
        return await env.resources.list(kind=KIND) == []

    await wait_until(gone)
    assert (await s.history(booked["id"]))[0].run_id == run.run_id


@pytest.mark.acceptance(
    spec="channels", scenario="a follow-up answers in its thread and mentions the asker"
)
async def test_a_follow_up_answers_in_its_thread_mentioning_the_asker(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel = await env.register_channel("st")
    adapter = env.bind(
        channel,
        FakeChannelAdapter(
            supports_edit=False, supports_live_text=False, mention_template=_MENTION
        ),
    )
    await env.pair(channel, "owner", sender_id="owner-1")
    await env.pair(channel, "grp", sender_id="owner-1")
    env.provider.adapter = default_reply_adapter("Deploy is live.")
    args = s.in_turn("conv-1", channel, "grp", chat_kind="group", thread_id="th-1", asker="sam")
    booked = await s.tools.schedule({**args, "after": "1h", "prompt": "check the deploy"})
    s.clock.advance(timedelta(hours=1))
    await s.tick()
    (run,) = await s.settled(booked["id"])
    await wait_until(lambda: any("Deploy is live." in t for t in adapter.texts()))
    (routed,) = [r for r in adapter.sent_routed if "Deploy is live." in r[1]]
    assert routed == ("grp", "<@sam> Deploy is live.", "th-1", "group")
    assert await env.active_conversation(channel, "grp", "th-1") == run.conversation_id


# --- the daily report --------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="the daily report is set from the Channels page")
async def test_the_daily_report_is_set_and_moved(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, _ = await env.paired_channel()
    first = await s.tasks.daily_report(channel_uid=channel.uid, time="18:30", actor="t")
    assert first.name == "Daily report"
    assert first.config["schedule"] == {"kind": "daily", "time": "18:30"}
    assert first.config["chat"]["chat_id"] == "owner"
    assert first.config["session"] == "fresh" and first.config["material"] == "channel_day"
    moved = await s.tasks.daily_report(channel_uid=channel.uid, time="19:00", actor="t")
    assert moved.uid == first.uid
    assert [t.config["schedule"]["time"] for t in await env.resources.list(kind=KIND)] == ["19:00"]


@pytest.mark.acceptance(spec="channels", scenario="the report is given the day's conversations")
async def test_the_daily_report_reads_today_s_conversations(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "why is login failing?"))
    await wait_until(lambda: "Hello world" in adapter.texts())
    asked = await env.active_conversation(channel)
    await s.tasks.daily_report(channel_uid=channel.uid, time="18:00", actor="t")
    (task,) = await env.resources.list(kind=KIND)
    env.provider.adapter = default_reply_adapter("Today: one login question.")
    s.clock.now = START.replace(hour=18)
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "replied" and run.conversation_id != asked
    prompt = env.raw_prompts(run.conversation_id)[0]
    assert f"[{MATERIAL}]" in prompt
    assert "Channel conversations since" in prompt


@pytest.mark.acceptance(spec="channels", scenario="a quiet day sends no report")
async def test_a_quiet_day_sends_no_report(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, adapter = await env.paired_channel()
    task = await s.tasks.daily_report(channel_uid=channel.uid, time="18:00", actor="t")
    s.clock.now = START.replace(hour=18)
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "skipped" and run.reason == "no channel conversations today"
    await asyncio.sleep(0.05)
    assert adapter.texts() == []


# --- /status -------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="/status lists a waiting follow-up with its Cancel button"
)
async def test_status_lists_and_cancels_a_waiting_follow_up(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel = await env.register_channel("tg")
    adapter = env.bind(channel, FakeChannelAdapter(supports_buttons=True))
    await env.pair(channel, "owner")
    args = s.in_turn("conv-1", channel)
    booked = await s.tools.schedule(
        {**args, "at": "2026-10-29T15:00", "prompt": "check", "name": "Deploy check"}
    )
    await env.processor.on_message(inbound("tg", "owner", "/status"))
    (_chat, text, buttons) = adapter.cards[-1]
    assert "Scheduled:" in text.splitlines()
    assert any(line.startswith("⏰ 1. ") and "Deploy check" in line for line in text.splitlines())
    cancel = next(b for b in buttons if b.label == "Cancel ⏰1")
    assert cancel.value == f"{TASK_CANCEL_KIND}:{booked['id']}"
    await env.processor.on_callback(tap_event("tg", "owner", cancel.value))
    await wait_until(lambda: any("Cancelled" in t for t in adapter.texts()))
    assert await env.resources.list(kind=KIND) == []
