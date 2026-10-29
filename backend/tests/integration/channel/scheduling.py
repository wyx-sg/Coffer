"""The scheduled-task stack over a ``ChannelEnv``, wired as ``schedule_wiring``
wires it in the daemon, on a clock the test moves."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application import resource_service
from coffer.application.channel import turn_origin
from coffer.application.channel.schedule.kind import KIND, make_scheduled_task_kind
from coffer.application.channel.schedule.material import channel_day, day_conversations
from coffer.application.channel.schedule.runner import TaskRunner
from coffer.application.channel.schedule.scheduler import TaskScheduler
from coffer.application.channel.schedule.tasks import TaskService
from coffer.application.channel.schedule.tools import ScheduleTools
from coffer.application.turn_scope import TURN_ARGUMENT
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.resource import Resource
from coffer.infrastructure.channel.persistence import ScheduledRunRepo
from coffer.infrastructure.persistence.engine import session_maker

from .conftest import ChannelEnv, wait_until

#: Thursday 2026-10-29, 10:00 UTC: every test starts here.
START = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        self.now += by


class _ClockedDatetime(datetime):
    """``datetime`` whose ``now`` is the test clock, for the resource service, so
    a task is created at the test's time: its first slot is counted from it."""

    clock: Clock | None = None

    @classmethod
    def now(cls, tz: Any = None) -> Any:
        if cls.clock is None:
            return datetime.now(tz)
        return cls.clock.now if tz is None else cls.clock.now.astimezone(tz)


@dataclass
class Scheduling:
    env: ChannelEnv
    clock: Clock
    runs: ScheduledRunRepo
    runner: TaskRunner
    scheduler: TaskScheduler
    tasks: TaskService
    tools: ScheduleTools
    notices: list[tuple[str, str]] = field(default_factory=list)
    #: turn token -> conversation, as the gateway's turn tokens answer it.
    tokens: dict[str, str] = field(default_factory=dict)

    async def tick(self) -> None:
        """One scheduler pass, as the loop would run it now."""
        await self.scheduler._pass(False)

    async def history(self, task_uid: str) -> list[ScheduledRun]:
        return await self.runs.for_task(task_uid, limit=50)

    async def settled(self, task_uid: str, count: int = 1) -> list[ScheduledRun]:
        """Wait until ``count`` runs of the task have ended; its history."""

        async def done() -> bool:
            rows = await self.history(task_uid)
            return len([r for r in rows if r.outcome != "running"]) >= count

        await wait_until(done)
        return await self.history(task_uid)

    def in_turn(
        self,
        conversation_id: str,
        channel: Resource,
        chat_id: str = "owner",
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
        owner: bool = True,
        asker: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        """The tool arguments of a call made inside a channel turn on
        ``conversation_id``: the turn's origin is remembered, as the turn
        driver does while it renders, and the gateway's turn argument added."""
        turn_origin.remember(
            conversation_id,
            turn_origin.TurnOrigin(
                channel_uid=channel.uid,
                chat_id=chat_id,
                chat_kind=chat_kind,
                thread_id=thread_id,
                conversation_thread_id=thread_id,
                asker_is_owner=owner,
                mention_user_id=asker,
                mention_user_name=asker,
                **extra,
            ),
        )
        token = f"tok-{conversation_id}"
        self.tokens[token] = conversation_id
        return {TURN_ARGUMENT: token}


def build_scheduling(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch, clock: Clock | None = None
) -> Scheduling:
    clock = clock or Clock()
    monkeypatch.setattr(_ClockedDatetime, "clock", clock)
    monkeypatch.setattr(resource_service, "datetime", _ClockedDatetime)
    runs = ScheduledRunRepo(session_maker(env.engine))
    holder: dict[str, Any] = {}

    async def material(task: Resource, now: datetime) -> str:
        since = now - timedelta(hours=12)

        async def page(cursor: str | None) -> tuple[list[Any], str | None]:
            got = await env.chat.page_conversations(limit=50, cursor=cursor)
            return list(got.items), got.next_cursor

        today = await runs.since(since)
        found, total = await day_conversations(
            since=since,
            page=page,
            threads=env.threads,
            tails=None,
            channel_names={},
            exclude={r.conversation_id for r in today if r.task_uid == task.uid},
        )
        return channel_day(
            since=since,
            conversations=found,
            total=total,
            runs=[r for r in today if r.task_uid != task.uid],
            waiting=[],
        )

    async def notify(task: Resource, text: str) -> None:
        holder["s"].notices.append((task.uid, text))

    runner = TaskRunner(
        runs=runs,
        binding=env.processor.binding,
        peers=env.peers,
        threads=env.threads,
        conversations=env.chat,
        driver=lambda: env.processor.turn_driver,
        material=material,
        clock=clock,
    )
    scheduler = TaskScheduler(
        resources=env.resources, runs=runs, runner=runner, notify=notify, clock=clock
    )
    tasks = TaskService(
        resources=env.resources,
        runs=runs,
        peers=env.peers,
        next_run=scheduler.next_run,
        is_running=scheduler.is_running,
        clock=clock,
    )

    async def channel_uids() -> set[str]:
        return {r.uid for r in await env.resources.list(kind="channel")}

    async def paired(channel_uid: str, chat_id: str) -> bool:
        return await env.peers.get_by_chat(channel_uid, chat_id) is not None

    env.kinds[KIND] = make_scheduled_task_kind(channels=channel_uids, paired=paired, clock=clock)
    env.processor.commands.scheduled = tasks
    scheduling = Scheduling(
        env=env,
        clock=clock,
        runs=runs,
        runner=runner,
        scheduler=scheduler,
        tasks=tasks,
        tools=ScheduleTools(
            tasks=tasks,
            resources=env.resources,
            conversation_of=lambda token: holder["s"].tokens.get(token or ""),
            clock=clock,
        ),
    )
    holder["s"] = scheduling
    return scheduling


def daily(time: str = "10:30") -> dict[str, Any]:
    return {"kind": "daily", "time": time}


def task_config(
    channel: Resource,
    chat_id: str = "owner",
    *,
    schedule: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schedule": schedule or daily(),
        "prompt": "Summarise the open pull requests",
        "chat": {"channel": channel.uid, "chat_id": chat_id},
        **extra,
    }
