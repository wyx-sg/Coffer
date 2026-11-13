"""Scheduled tasks end to end through the real chat platform (spec scheduled-tasks
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
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from coffer.application.channel.schedule.attention import ScheduledTaskAttentionSource
from coffer.application.channel.schedule.kind import KIND
from coffer.domain.chat.events import TurnError, TurnStarted
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import StorageClass
from coffer.infrastructure.channel.persistence import ScheduledRunModel
from coffer.infrastructure.persistence.engine import session_maker
from coffer.surfaces.http import errors
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.schedule_routes import router as schedule_router
from coffer.surfaces.http.schedule_routes import set_schedule_services
from coffer.surfaces.http.schedule_wiring import _Reads
from tests.unit.chat.conftest import FakeAgentAdapter

from .conftest import ChannelEnv, default_reply_adapter
from .scheduling import PROMPT, START, build_scheduling, daily, task_config
from .test_queue_and_stop import GatedAdapter


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


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a task is created")
async def test_a_task_is_created(env: ChannelEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    s = build_scheduling(env, monkeypatch)
    env.add_agent("codex")
    task = await s.tasks.create(
        None,
        task_config(
            agent="codex",
            schedule={"kind": "daily", "time": "11:00", "timezone": "Asia/Singapore"},
        ),
        actor="test",
        prompt="Summarise the open pull requests",
    )
    assert task.kind == KIND
    assert env.resources.storage_of(KIND, task.config) is StorageClass.LOCAL
    assert task.name == "Summarise the open pull requests"
    assert task.config["agent"] == "codex" and task.config["cwd"] is None
    assert "chat" not in task.config
    view = await s.tasks.view(task.uid)
    # Thursday 10:00 UTC is 18:00 in Singapore: the next 11:00 there is
    # Friday's, 03:00 UTC.
    assert view.next_run == datetime(2026, 10, 30, 3, 0, tzinfo=UTC)


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a task without an agent is refused")
async def test_a_task_without_an_agent_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    config = task_config()
    config.pop("agent")
    with pytest.raises(ConfigValidationError, match="agent"):
        await s.tasks.create(None, config, actor="test", prompt="p")
    # A chat is no part of a task now.
    with pytest.raises(ConfigValidationError, match="chat"):
        await s.tasks.create(
            None, task_config(chat={"channel": "c", "chat_id": "owner"}), actor="test", prompt="p"
        )
    # The generic create holds the same rules.
    with pytest.raises(ConfigValidationError):
        await env.resources.register(KIND, "x", config, "test")
    assert await env.resources.list(kind=KIND) == []


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a schedule closer than 15 minutes is refused"
)
async def test_a_schedule_closer_than_fifteen_minutes_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    with pytest.raises(ConfigValidationError, match="15 minutes"):
        await s.tasks.create(
            None,
            task_config(schedule={"kind": "cron", "expr": "*/5 * * * *"}),
            actor="test",
            prompt="p",
        )
    past = (START - timedelta(minutes=1)).isoformat()
    with pytest.raises(ConfigValidationError):
        await s.tasks.create(
            None, task_config(schedule={"kind": "once", "at": past}), actor="test", prompt="p"
        )
    # Monday to Friday is a cron expression now; the shape is gone.
    with pytest.raises(ConfigValidationError):
        await s.tasks.create(
            None,
            task_config(schedule={"kind": "weekdays", "time": "09:00"}),
            actor="test",
            prompt="p",
        )


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="an unknown timezone is refused")
async def test_an_unknown_timezone_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    with pytest.raises(ConfigValidationError, match="Mars/Olympus"):
        await s.tasks.create(
            None,
            task_config(schedule={"kind": "daily", "time": "09:00", "timezone": "Mars/Olympus"}),
            actor="test",
            prompt="p",
        )
    assert await env.resources.list(kind=KIND) == []


# --- running on time ---------------------------------------------------------


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a daily task runs at its time")
async def test_a_daily_task_runs_at_its_time(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("Two PRs are open.")
    task = await s.create(task_config(schedule=daily("10:30")))

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


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a one-off task is switched off after it runs"
)
async def test_a_one_off_task_is_switched_off_after_it_runs(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    at = (START + timedelta(minutes=30)).isoformat()
    task = await s.create(task_config(schedule={"kind": "once", "at": at}))
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "done"
    assert not (await env.resources.get(task.uid)).enabled


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a slot whose previous run is still going is skipped"
)
async def test_a_slot_whose_previous_run_is_still_going_is_skipped(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    gated = GatedAdapter()
    env.provider.adapter = gated
    task = await s.create(task_config(schedule={"kind": "hourly", "minute": 0}))
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
    spec="scheduled-tasks", scenario="a daily task missed this morning runs late, once"
)
async def test_a_missed_daily_slot_runs_late_once(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config(schedule=daily("10:30")))
    s.clock.advance(timedelta(hours=3))  # asleep until 13:00
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.catch_up and run.outcome == "done"
    (prompt,) = env.raw_prompts(run.conversation_id)
    assert prompt.startswith("Summarise the open pull requests\n\n")
    assert "due at 2026-10-29 10:30" in prompt and "late, at 2026-10-29 13:00" in prompt


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a week of missed daily slots runs once")
async def test_a_week_of_missed_slots_runs_once(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config(schedule=daily("10:30")))
    s.clock.advance(timedelta(days=7, hours=1))  # a week later, 11:00
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.due_at == START.replace(minute=30) + timedelta(days=7)
    await s.tick()
    assert len(await s.history(task.uid)) == 1


@pytest.mark.acceptance(
    spec="scheduled-tasks",
    scenario="an evening task slept through overnight runs the next morning",
)
async def test_an_evening_task_slept_through_runs_the_next_morning(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config(schedule=daily("23:00")))
    s.clock.now = START.replace(hour=8) + timedelta(days=1)  # asleep 22:50 to 08:00
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.catch_up and run.outcome == "done"
    assert run.due_at == START.replace(hour=23)


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a slot missed more than seven days ago is skipped"
)
async def test_a_slot_missed_more_than_seven_days_ago_is_skipped(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    at = (START + timedelta(minutes=30)).isoformat()
    task = await s.create(task_config(schedule={"kind": "once", "at": at}))
    s.clock.advance(timedelta(days=8))
    await s.tick()
    (run,) = await s.history(task.uid)
    assert run.outcome == "skipped" and "missed" in run.reason
    assert not (await env.resources.get(task.uid)).enabled


async def test_a_one_off_missed_by_a_day_still_runs_late(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    at = (START + timedelta(minutes=30)).isoformat()
    task = await s.create(task_config(schedule={"kind": "once", "at": at}))
    s.clock.advance(timedelta(days=1))
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.catch_up and run.outcome == "done"


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a task that does not catch up skips a late slot"
)
async def test_a_task_that_does_not_catch_up_skips_a_late_slot(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config(schedule=daily("10:30"), catch_up=False))
    s.clock.advance(timedelta(hours=1))
    await s.tick()
    (run,) = await s.history(task.uid)
    assert run.outcome == "skipped"


# --- pausing and editing --------------------------------------------------------


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="resuming a paused task starts nothing")
async def test_resuming_a_paused_task_starts_nothing(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config(schedule=daily("10:30")))
    await env.resources.set_enabled(task.uid, False, "t")
    await s.tick()
    s.clock.advance(timedelta(days=3, hours=5))  # three days on, 15:00
    await env.resources.set_enabled(task.uid, True, "t")
    await s.tick()
    assert await s.history(task.uid) == []
    view = await s.tasks.view(task.uid)
    assert view.next_run == START.replace(minute=30) + timedelta(days=4)
    # A restart in between changes nothing: where it counts from is kept.
    again = build_scheduling(env, monkeypatch, s.clock)
    await again.tick()
    assert await again.history(task.uid) == []


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="editing a task's time starts nothing")
async def test_editing_a_task_s_time_starts_nothing(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("ok")
    task = await s.create(task_config(schedule=daily("18:00")))
    s.clock.now = START.replace(hour=18)
    await s.tick()
    await s.settled(task.uid)
    s.clock.now = START.replace(hour=12) + timedelta(days=1)  # noon the next day
    await env.resources.update_config(task.uid, task_config(schedule=daily("08:00")), "t")
    await s.tick()
    assert len(await s.history(task.uid)) == 1
    view = await s.tasks.view(task.uid)
    assert view.next_run == START.replace(hour=8) + timedelta(days=2)


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a one-off whose time has passed is not resumed"
)
async def test_a_one_off_whose_time_has_passed_is_not_resumed(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    at = (START + timedelta(minutes=30)).isoformat()
    task = await s.create(task_config(schedule={"kind": "once", "at": at}))
    await env.resources.set_enabled(task.uid, False, "t")
    s.clock.advance(timedelta(hours=1))
    with pytest.raises(ConfigValidationError, match="past"):
        await env.resources.set_enabled(task.uid, True, "t")
    assert not (await env.resources.get(task.uid)).enabled


async def test_pruned_history_does_not_bring_an_old_slot_back(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("ok")
    task = await s.create(task_config(schedule=daily("10:30")))
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    await s.settled(task.uid)
    # Retention removes the row; the slot it was for stays settled.
    async with session_maker(env.engine)() as session:
        await session.execute(delete(ScheduledRunModel))
        await session.commit()
    s.clock.advance(timedelta(hours=1))
    await s.tick()
    assert await s.history(task.uid) == []


async def test_a_run_that_cannot_be_recorded_does_not_leave_the_task_running(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config(schedule=daily("10:30")))

    async def broken(_run: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(s.runs, "add", broken)
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    assert not s.scheduler.is_running(task.uid)


# --- the conversation ------------------------------------------------------------


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a task runs in a new conversation of its own each time"
)
async def test_a_task_runs_in_a_new_conversation_each_time(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    channel, adapter = await env.paired_channel()
    env.provider.adapter = default_reply_adapter("The build is green.")
    task = await s.create(task_config(schedule=daily("10:30")), "Nightly build")

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
        assert conversation.channel_uid is None
        assert conversation.title == "Nightly build"
        assert env.raw_prompts(run.conversation_id) == ["Summarise the open pull requests"]
    assert first.conversation_id != second.conversation_id
    # Nothing was posted to any chat, and the chat's own conversation is untouched.
    assert adapter.texts() == []
    assert await env.active_conversation(channel) is None


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a task that names no folder runs in its own"
)
async def test_a_task_that_names_no_folder_runs_in_its_own(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("Done.")
    task = await s.create(task_config(schedule=daily("10:30")), "Tidy")

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)

    conversation = await env.chat.get_conversation(run.conversation_id)
    folder = (await s.tasks.view(task.uid)).folder
    assert conversation.agent_config.cwd == folder
    assert folder.endswith(f"/.coffer/content/workspace/scheduled-tasks/{task.uid}")


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a task runs in the folder it names")
async def test_a_task_runs_in_the_folder_it_names(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    s = build_scheduling(env, monkeypatch)
    adapter = default_reply_adapter("Done.")
    env.provider.adapter = adapter
    repo = tmp_path / "repo"
    repo.mkdir()
    task = await s.create(task_config(schedule=daily("10:30"), cwd=str(repo)), "Tidy")

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)

    conversation = await env.chat.get_conversation(run.conversation_id)
    assert conversation.agent_config.cwd == str(repo)
    # The prompt stays in the task's own folder, not the one its runs work in.
    view = await s.tasks.view(task.uid)
    assert Path(view.folder, "PROMPT.md").read_text(encoding="utf-8").strip() == PROMPT
    assert not (repo / "PROMPT.md").exists()


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a run whose folder is gone fails")
async def test_a_run_whose_folder_is_gone_fails(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("Done.")
    gone = tmp_path / "gone"
    task = await s.create(task_config(schedule=daily("10:30"), cwd=str(gone)))

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)

    assert run.outcome == "failed"
    assert run.reason == f"its folder {gone} does not exist"
    assert run.conversation_id == ""


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a folder that is not an absolute path is refused"
)
async def test_a_folder_that_is_not_an_absolute_path_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    with pytest.raises(ConfigValidationError, match="absolute path"):
        await s.create(task_config(cwd="notes/reports"))
    assert await env.resources.list(kind=KIND) == []


# --- the prompt file -----------------------------------------------------------


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a task's prompt is the PROMPT.md in its folder"
)
async def test_the_prompt_is_a_file_in_the_task_folder(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config())
    assert "prompt" not in task.config
    view = await s.tasks.view(task.uid)
    assert view.prompt == "Summarise the open pull requests\n"
    assert (Path(view.folder) / "PROMPT.md").read_text() == view.prompt


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="the next run is given the prompt as edited"
)
async def test_the_next_run_is_given_the_prompt_as_edited(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = adapter = default_reply_adapter("Done.")
    task = await s.create(task_config())
    await s.tasks.set_prompt(task.uid, "# Daily\n\nCount the open issues.")
    folder = Path((await s.tasks.view(task.uid)).folder)
    (folder / "PROMPT.md").write_text("# Daily\n\nCount the closed issues.\n")

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    await s.settled(task.uid)
    assert "Count the closed issues." in adapter.recorded_prompts[-1]


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a run whose PROMPT.md is missing fails")
async def test_a_run_whose_prompt_file_is_missing_fails(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config())
    (Path((await s.tasks.view(task.uid)).folder) / "PROMPT.md").unlink()

    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    (run,) = await s.settled(task.uid)
    assert run.outcome == "failed"
    assert run.reason == "PROMPT.md is missing or empty"


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a task without a prompt is refused")
async def test_a_task_without_a_prompt_is_refused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    for blank in ("", "   \n"):
        with pytest.raises(ConfigValidationError, match="prompt"):
            await s.tasks.create("Nightly build", task_config(), actor="t", prompt=blank)
    assert await env.resources.list(kind=KIND) == []
    task = await s.create(task_config(), "Nightly build")
    assert task.enabled is True


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a prompt in a task's file is refused on edit"
)
async def test_a_prompt_in_the_task_file_is_refused_on_edit(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config())
    with pytest.raises(ConfigValidationError, match=r"PROMPT\.md"):
        await env.resources.update_config(task.uid, {**task.config, "prompt": "Other"}, "t")


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a task whose turn fails is recorded failed"
)
async def test_a_task_whose_turn_fails_is_recorded_failed(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    _, adapter = await env.paired_channel()
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    task = await s.create(task_config())
    run = await s.scheduler.run_now(await env.resources.get(task.uid))
    (ended,) = await s.settled(task.uid)
    assert ended.run_id == run.run_id
    assert ended.outcome == "failed" and ended.reason == "upstream timed out"
    assert adapter.texts() == []


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a repeating task that keeps failing is paused"
)
async def test_a_repeating_task_that_keeps_failing_is_paused(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    task = await s.create(task_config(schedule=daily("10:30")))
    for day in range(3):
        s.clock.now = START.replace(minute=30) + timedelta(days=day)
        await s.tick()
        await s.settled(task.uid, count=day + 1)
    rows = await s.history(task.uid)
    assert [r.outcome for r in rows] == ["failed"] * 3
    assert not (await env.resources.get(task.uid)).enabled


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a task paused for failing is listed in Needs you"
)
async def test_a_task_paused_for_failing_is_listed_in_needs_you(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = FakeAgentAdapter(
        [TurnStarted(), TurnError(code="PROVIDER_TIMEOUT", message="upstream timed out")]
    )
    attention = ScheduledTaskAttentionSource(resources=env.resources, runs=s.runs)
    task = await s.create(task_config(schedule=daily("10:30")), "Morning digest")
    for day in range(3):
        assert await attention.items() == []
        s.clock.now = START.replace(minute=30) + timedelta(days=day)
        await s.tick()
        await s.settled(task.uid, count=day + 1)

    (item,) = await attention.items()
    assert (item.kind, item.uid, item.title) == (KIND, task.uid, "Morning digest")
    assert item.reason_code == "scheduled_task_paused_failing"
    assert "upstream timed out" in item.reason

    await env.resources.set_enabled(task.uid, True, actor="t")
    assert await attention.items() == []


# --- history -------------------------------------------------------------------


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="a run's history row says how it ended")
async def test_the_history_says_how_each_run_ended(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config(schedule=daily("10:30"), catch_up=False))
    s.clock.advance(timedelta(hours=1))  # missed, no catch-up
    await s.tick()
    s.clock.advance(timedelta(days=1, minutes=-30))  # tomorrow 10:30, on time
    await s.tick()
    rows = await s.settled(task.uid, count=2)
    assert [r.outcome for r in rows] == ["done", "skipped"]
    assert rows[0].conversation_id and rows[1].reason


@pytest.mark.acceptance(
    spec="scheduled-tasks", scenario="a run's conversation opens from its history"
)
async def test_the_history_names_each_run_s_conversation(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    task = await s.create(task_config())
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
    spec="scheduled-tasks", scenario="a run interrupted by a stop is closed on the next start"
)
async def test_a_run_left_open_is_closed_on_start(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    gated = GatedAdapter()
    env.provider.adapter = gated
    task = await s.create(task_config())
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    await gated.entered.wait()
    # A daemon that starts again finds the row still open.
    closed = await s.runs.close_interrupted(
        reason="Coffer stopped while it was running", finished_at=s.clock()
    )
    assert closed == 1
    (row,) = await s.history(task.uid)
    assert row.outcome == "stopped" and "stopped" in row.reason
    gated.release.set()


@pytest.mark.acceptance(spec="scheduled-tasks", scenario="the owner runs a task now from the page")
async def test_run_now_runs_a_paused_task_once(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = build_scheduling(env, monkeypatch)
    env.provider.adapter = default_reply_adapter("ran by hand")
    task = await s.create(task_config(schedule={"kind": "weekly", "weekday": 0, "time": "09:00"}))
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
    task = await s.create(task_config())
    switch = {"on": False}
    s.scheduler._enabled = lambda: switch["on"]
    s.clock.advance(timedelta(minutes=30))
    await s.tick()
    assert await s.history(task.uid) == []
    # Switched on: the slot that just passed runs, late.
    switch["on"] = True
    await s.tick()
    (row,) = await s.settled(task.uid)
    assert row.outcome == "done"


# --- the routes the detail page uses ------------------------------------------


@pytest.mark.acceptance(
    spec="scheduled-tasks",
    scenario="the owner reads and edits a task's prompt on its page",
)
async def test_the_page_edits_the_prompt(env: ChannelEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    s = build_scheduling(env, monkeypatch)
    set_schedule_services(tasks=s.tasks, scheduler=s.scheduler, reads=None)
    set_active_token("t")
    app = FastAPI()
    errors.register(app)
    app.include_router(schedule_router)
    headers = {"X-Coffer-Token": "t"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://x", headers=headers
    ) as c:
        made = await c.post(
            "/api/v1/scheduled-tasks",
            json={
                "prompt": "# Report\n\nWrite today's report to report.md.",
                "config": {"schedule": daily(), "agent": "builtin"},
            },
        )
        assert made.status_code == 201, made.text
        task = made.json()
        assert task["prompt"] == "# Report\n\nWrite today's report to report.md.\n"
        uid = task["uid"]

        edited = await c.put(f"/api/v1/scheduled-tasks/{uid}/prompt", json={"prompt": "Say hi"})
        assert edited.json()["prompt"] == "Say hi\n"
        assert (Path(task["folder"]) / "PROMPT.md").read_text() == "Say hi\n"
