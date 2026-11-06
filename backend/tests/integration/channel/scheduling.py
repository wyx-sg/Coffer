"""The scheduled-task stack over a ``ChannelEnv`` (for its chat platform),
wired as ``schedule_wiring`` wires it in the daemon, on a clock the test moves."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application import resource_service
from coffer.application.channel.schedule.kind import KIND, make_scheduled_task_kind
from coffer.application.channel.schedule.runner import TaskRunner
from coffer.application.channel.schedule.scheduler import TaskScheduler
from coffer.application.channel.schedule.tasks import TaskService
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.infrastructure.channel.persistence import ScheduledRunRepo
from coffer.infrastructure.persistence.engine import session_maker
from coffer.surfaces.http.schedule_wiring import FreshTurns

from .conftest import ChannelEnv, wait_until

#: Thursday 2026-10-29, 10:00 UTC: every test starts here.
START = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: Any) -> None:
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


def build_scheduling(
    env: ChannelEnv, monkeypatch: pytest.MonkeyPatch, clock: Clock | None = None
) -> Scheduling:
    clock = clock or Clock()
    monkeypatch.setattr(_ClockedDatetime, "clock", clock)
    monkeypatch.setattr(resource_service, "datetime", _ClockedDatetime)
    runs = ScheduledRunRepo(session_maker(env.engine))
    runner = TaskRunner(runs=runs, fresh=FreshTurns(env.chat, env.orchestrator), clock=clock)
    scheduler = TaskScheduler(resources=env.resources, runs=runs, runner=runner, clock=clock)
    tasks = TaskService(
        resources=env.resources,
        runs=runs,
        next_run=scheduler.next_run,
        is_running=scheduler.is_running,
    )
    env.kinds[KIND] = make_scheduled_task_kind(clock=clock)
    return Scheduling(
        env=env, clock=clock, runs=runs, runner=runner, scheduler=scheduler, tasks=tasks
    )


def daily(time: str = "10:30") -> dict[str, Any]:
    return {"kind": "daily", "time": time}


def task_config(
    *, schedule: dict[str, Any] | None = None, agent: str = "builtin", **extra: Any
) -> dict[str, Any]:
    return {
        "schedule": schedule or daily(),
        "prompt": "Summarise the open pull requests",
        "agent": agent,
        **extra,
    }
