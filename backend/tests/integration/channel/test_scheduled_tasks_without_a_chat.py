"""Scheduled tasks bound to no chat, end to end through the real chat platform
(spec channels "Keep scheduled tasks as machine-local resources", "Run a task
bound to no chat in a fresh conversation of its own").

A task that names no chat runs like an automation of Claude Code or Codex: each
run is a fresh conversation of the task's own agent in its own directory, and
its answer stays there. The clock is the test's; the turn is a real turn
through the orchestrator."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.channel import turn_origin
from coffer.application.channel.schedule.kind import KIND
from coffer.domain.chat.events import TurnError, TurnStarted
from coffer.domain.errors import ConfigValidationError
from coffer.domain.turn_markers import SCHEDULED
from tests.unit.chat.conftest import FakeAgentAdapter

from .conftest import ChannelEnv, default_reply_adapter
from .scheduling import START, build_scheduling, daily, no_chat_config


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


@pytest.mark.acceptance(spec="channels", scenario="a task in no chat is created")
async def test_a_task_in_no_chat_is_created(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.add_agent("codex")
    task = await s.tasks.create(
        None,
        no_chat_config(
            agent="codex",
            cwd="/tmp/site",
            schedule={"kind": "weekdays", "time": "11:00", "timezone": "Asia/Singapore"},
        ),
        actor="test",
    )
    assert task.kind == KIND
    assert "chat" not in task.config
    assert task.config["schedule"]["timezone"] == "Asia/Singapore"
    view = await s.tasks.view(task.uid)
    # Thursday 10:00 UTC is 18:00 in Singapore: the next 11:00 there is
    # Friday's, 03:00 UTC.
    assert view.next_run == datetime(2026, 10, 30, 3, 0, tzinfo=UTC)


@pytest.mark.acceptance(spec="channels", scenario="a task in no chat without an agent is refused")
async def test_a_task_in_no_chat_without_an_agent_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    config = no_chat_config()
    config.pop("agent")
    with pytest.raises(ConfigValidationError, match="names the agent"):
        await s.tasks.create(None, config, actor="test")
    with pytest.raises(ConfigValidationError, match="every run is fresh"):
        await s.tasks.create(None, no_chat_config(session="continue"), actor="test")
    assert await env.resources.list(kind=KIND) == []


@pytest.mark.acceptance(spec="channels", scenario="an unknown timezone is refused")
async def test_an_unknown_timezone_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    with pytest.raises(ConfigValidationError, match="Mars/Olympus"):
        await s.tasks.create(
            None,
            no_chat_config(schedule={"kind": "daily", "time": "09:00", "timezone": "Mars/Olympus"}),
            actor="test",
        )
    assert await env.resources.list(kind=KIND) == []


@pytest.mark.acceptance(
    spec="channels", scenario="a task in no chat runs in a new conversation of its own"
)
async def test_a_task_in_no_chat_runs_in_a_new_conversation_each_time(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, adapter = await env.paired_channel()
    env.provider.adapter = default_reply_adapter("The build is green.")
    task = await s.tasks.create(
        "Nightly build", no_chat_config(cwd="/tmp/site", schedule=daily("10:30")), actor="t"
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
        assert run.channel_uid == "" and run.chat_id == ""
        conversation = await env.chat.get_conversation(run.conversation_id)
        assert conversation.agent_key == "builtin"
        assert conversation.agent_config.cwd == "/tmp/site"
        assert conversation.channel_uid is None
        assert conversation.title == "Nightly build"
        prompt = env.raw_prompts(run.conversation_id)[0]
        assert prompt.startswith(f"[{SCHEDULED}]")
        assert "channel id:" not in prompt and "[SILENT]" not in prompt
        assert "coffer__channel_notify" in prompt
    assert first.conversation_id != second.conversation_id
    # Nothing was posted to any chat, and the chat's own conversation is untouched.
    assert adapter.texts() == []
    assert await env.active_conversation(channel) is None


@pytest.mark.acceptance(
    spec="channels", scenario="a task in no chat whose turn fails is recorded failed"
)
async def test_a_task_in_no_chat_whose_turn_fails_is_recorded_failed(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    _, adapter = await env.paired_channel()
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    task = await s.tasks.create(None, no_chat_config(), actor="t")
    (run,) = [await s.scheduler.run_now(await env.resources.get(task.uid))]
    (ended,) = await s.settled(task.uid)
    assert ended.run_id == run.run_id
    assert ended.outcome == "failed" and ended.reason == "upstream timed out"
    assert adapter.texts() == []


async def test_a_task_in_no_chat_that_keeps_failing_is_paused_without_a_notice(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    task = await s.tasks.create(None, no_chat_config(schedule=daily("10:30")), actor="t")
    for day in range(3):
        s.clock.now = START.replace(minute=30) + timedelta(days=day)
        await s.tick()
        await s.settled(task.uid, count=day + 1)
    assert not (await env.resources.get(task.uid)).enabled
    # The pause notice goes to a task's chat; this one has none (the test's
    # ``notify`` records whatever the scheduler asks it to send).
    assert all(uid != task.uid or "paused" in text for uid, text in s.notices)
