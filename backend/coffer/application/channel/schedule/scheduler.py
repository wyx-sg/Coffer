"""The worker that starts scheduled tasks on time (spec channels "Run a
scheduled task at the times it names" and "Catch up a missed run once, within
its grace").

It sleeps until the earliest slot any enabled task names, on the shared
wakeable loop, and is woken early by every resource write (a task created,
edited, paused or removed) and by every run that ends. With no task waiting it
has no timer at all. A sleep is never longer than five minutes, because the
event loop's clock does not advance while a Mac sleeps: a wake is noticed
within five minutes, by the wall clock.

Each pass, for each enabled task whose next slot is due, it finds the most
recent slot it missed and decides once:

* within the task's grace (``grace_for``) and catch-up on → run it, saying it
  is late when it is more than a minute late;
* otherwise → record it skipped, with the reason, and move on to the next slot;
* the task's previous run is still going → record it skipped for that reason.

Older missed slots are never run: a daily task that missed a week runs once
(ADR scheduled-tasks-are-turns-coffer-starts-in-a-chat, "Missed runs").

Once a run has ended: a one-off is over — a follow-up the agent booked is
removed (its history stays), the owner's is switched off — and a repeating
task that has failed three times in a row is paused and the chat is told.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from coffer.application.channel.schedule.kind import KIND
from coffer.application.channel.schedule.ports import ScheduledRunRepoPort
from coffer.application.channel.schedule.runner import RunRequest, TaskRunner
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.wakeable import WakeableLoop
from coffer.application.runtime.workers import WorkerMode
from coffer.domain.channel.schedule import OnceSchedule, is_repeating, next_slot
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.channel.scheduled_task import ScheduledTaskConfig, grace_for
from coffer.domain.resource import Resource

__all__ = ["ACTOR", "FAILURES_BEFORE_PAUSE", "TaskScheduler"]

_logger = logging.getLogger(__name__)

#: Who the audit log names for what the scheduler does to a task by itself.
ACTOR = "coffer:scheduler"
#: A repeating task that fails this many runs in a row is paused.
FAILURES_BEFORE_PAUSE = 3
#: The longest sleep (see the module docstring).
_MAX_SLEEP = 300.0
#: How late a run may start and still not be called late.
_ON_TIME = timedelta(minutes=1)

#: Tells a task's chat something (the pause notice); best-effort.
Notify = Callable[[Resource, str], Awaitable[None]]


class TaskScheduler:
    def __init__(
        self,
        *,
        resources: ResourceService,
        runs: ScheduledRunRepoPort,
        runner: TaskRunner,
        notify: Notify | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._resources = resources
        self._runs = runs
        self._runner = runner
        self._notify = notify
        self._clock = clock
        #: Tasks with a run under way, by uid.
        self._running: set[str] = set()
        #: When the earliest enabled task is next due, for the loop's sleep.
        self._next_due: datetime | None = None
        runner.on_settled = self._settled
        self._loop = WakeableLoop(
            "scheduled-tasks",
            self._pass,
            fallback=self._sleep_for,
            mode=WorkerMode.EVENT_FALLBACK,
        )

    # -- the loop -----------------------------------------------------------

    def poke(self) -> None:
        self._loop.poke()

    def on_changed(self, _changed: object) -> None:
        """A resource write of any kind (a ``HintSink``)."""
        self.poke()

    async def serve(self) -> None:
        """Close the runs a stopped daemon left open, then run until cancelled."""
        await self._runs.close_interrupted(
            reason="Coffer stopped while it was running", finished_at=self._clock()
        )
        await self._pass(False)
        await self._loop.serve()

    def _sleep_for(self) -> float | None:
        if self._next_due is None:
            return None
        wait = (self._next_due - self._clock()).total_seconds()
        return min(max(wait, 0.0), _MAX_SLEEP)

    def is_running(self, task_uid: str) -> bool:
        return task_uid in self._running

    async def next_run(self, task: Resource) -> datetime | None:
        """When ``task`` runs next if nothing changes; ``None`` for none."""
        if not task.enabled:
            return None
        config = ScheduledTaskConfig.model_validate(task.config)
        last = await self._runs.latest_slot(task.uid)
        return next_slot(config.schedule, last or task.created_at)

    async def _pass(self, _poked: bool) -> None:
        now = self._clock()
        earliest: datetime | None = None
        for task in await self._resources.list(kind=KIND):
            if not task.enabled:
                continue
            try:
                due = await self._consider(task, now)
            except Exception:
                _logger.exception("channel.schedule.pass_failed", extra={"task": task.uid})
                continue
            if due is not None and (earliest is None or due < earliest):
                earliest = due
        self._next_due = earliest

    async def _consider(self, task: Resource, now: datetime) -> datetime | None:
        """Run or skip ``task``'s due slot; return when it is next due."""
        config = ScheduledTaskConfig.model_validate(task.config)
        last = await self._runs.latest_slot(task.uid)
        due = next_slot(config.schedule, last or task.created_at)
        if due is None or due > now:
            return due
        # The most recent slot at or before now; anything older is let go.
        slot = due
        while (following := next_slot(config.schedule, slot)) is not None and following <= now:
            slot = following
        request = RunRequest(task=task, due_at=slot, late=now - slot > _ON_TIME)
        grace = grace_for(config, slot=slot, created_at=task.created_at)
        if task.uid in self._running:
            await self._runner.skip(request, "the previous run was still going")
        elif now - slot > (grace if config.catch_up else _ON_TIME):
            await self._runner.skip(request, "missed: this computer was asleep or Coffer was off")
        else:
            self._running.add(task.uid)
            await self._runner.run(request)
        return next_slot(config.schedule, slot)

    async def run_now(self, task: Resource) -> ScheduledRun:
        """Run ``task`` once, now, whatever its schedule (Run now)."""
        if task.uid in self._running:
            raise ValueError("the task is already running")
        self._running.add(task.uid)
        return await self._runner.run(RunRequest(task=task, due_at=self._clock(), trigger="manual"))

    # -- after a run ----------------------------------------------------------

    async def _settled(self, task: Resource, run: ScheduledRun) -> None:
        if run.outcome != "skipped":
            self._running.discard(task.uid)
        try:
            await self._after(task, run)
        finally:
            self.poke()

    async def _after(self, task: Resource, run: ScheduledRun) -> None:
        config = ScheduledTaskConfig.model_validate(task.config)
        if isinstance(config.schedule, OnceSchedule) and run.trigger == "schedule":
            if run.outcome == "running":
                return
            if config.origin == "agent":
                await self._resources.delete(task.uid, ACTOR)
            else:
                await self._resources.set_enabled(task.uid, False, ACTOR)
            return
        if not is_repeating(config.schedule) or run.outcome != "failed":
            return
        recent = await self._runs.for_task(task.uid, limit=FAILURES_BEFORE_PAUSE)
        failed = [r for r in recent if r.outcome == "failed"]
        if len(recent) == FAILURES_BEFORE_PAUSE and len(failed) == FAILURES_BEFORE_PAUSE:
            await self._resources.set_enabled(task.uid, False, ACTOR)
            if self._notify is not None:
                await self._notify(
                    task,
                    f"⏸ Scheduled task “{task.name}” failed {FAILURES_BEFORE_PAUSE} times "
                    "in a row and is paused. Resume it on the Scheduled tasks page.",
                )
