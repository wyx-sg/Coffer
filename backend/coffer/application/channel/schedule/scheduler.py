"""The worker that starts scheduled tasks on time (spec scheduled-tasks "Run a
scheduled task at the times it names" and "Catch up a missed run once, within
seven days").

It sleeps until the earliest slot any enabled task names, on the shared
wakeable loop, and is woken early by every resource write (a task created,
edited, paused or removed) and by every run that ends. With no task waiting it
has no timer at all. A sleep is never longer than five minutes, because the
event loop's clock does not advance while a Mac sleeps: a wake is noticed
within five minutes, by the wall clock.

A task's slots are counted from its **anchor**: the last slot the scheduler
settled, or the moment it first saw the task switched on with the schedule it
has now. A task has an anchor only while it is on, so resuming one, or giving
it another schedule, starts counting from that moment: the slots it was paused
through are not missed, and nothing runs because a time was edited (ADR
a-missed-run-is-caught-up-within-seven-days).

Each pass, for each enabled task whose next slot is due, it finds the most
recent slot it missed and decides once:

* no more than seven days late and catch-up on → run it, saying it is late
  when it is more than a minute late;
* otherwise → record it skipped, with the reason, and move on to the next slot;
* the task's previous run is still going → record it skipped for that reason.

Older missed slots are never run: a daily task that missed a week runs once.

Once a run has ended: a one-off is over and is switched off, and a repeating
task that has failed three times in a row is paused; the page shows both.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from coffer.application.channel.schedule.kind import KIND
from coffer.application.channel.schedule.ports import (
    Anchor,
    ScheduledRunRepoPort,
    TaskAnchorPort,
)
from coffer.application.channel.schedule.runner import RunRequest, TaskRunner
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.wakeable import WakeableLoop
from coffer.application.runtime.workers import WorkerMode
from coffer.domain.channel.schedule import OnceSchedule, Schedule, is_repeating, next_slot
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.channel.scheduled_task import CATCH_UP_WINDOW, ScheduledTaskConfig
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


def _key(schedule: Schedule) -> str:
    """A schedule as the anchor remembers it: any change counts afresh."""
    return json.dumps(schedule.model_dump(mode="json"), sort_keys=True)


class TaskScheduler:
    def __init__(
        self,
        *,
        resources: ResourceService,
        runs: ScheduledRunRepoPort,
        runner: TaskRunner,
        anchors: TaskAnchorPort,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        enabled: Callable[[], bool] = lambda: True,
    ) -> None:
        self._resources = resources
        #: Whether the ``scheduled_tasks`` feature is on: while it is off no
        #: task runs, and a slot that passed is caught up or skipped as any
        #: missed slot is once it is switched back on.
        self._enabled = enabled
        self._runs = runs
        self._runner = runner
        self._anchors = anchors
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
        schedule = ScheduledTaskConfig.model_validate(task.config).schedule
        anchor = self._anchors.all().get(task.uid)
        counted = anchor.at if anchor and anchor.schedule == _key(schedule) else self._clock()
        return next_slot(schedule, counted)

    async def _pass(self, _poked: bool) -> None:
        if not self._enabled():
            self._next_due = None
            return
        now = self._clock()
        before = self._anchors.all()
        after: dict[str, Anchor] = {}
        earliest: datetime | None = None
        for task in await self._resources.list(kind=KIND):
            if not task.enabled:
                continue  # and its anchor goes: it counts afresh once resumed
            try:
                schedule = ScheduledTaskConfig.model_validate(task.config).schedule
                anchor = before.get(task.uid)
                if anchor is None or anchor.schedule != _key(schedule):
                    anchor = Anchor(schedule=_key(schedule), at=now)
                after[task.uid] = anchor
                due, settled = await self._consider(task, anchor.at, now)
                if settled is not None:
                    after[task.uid] = Anchor(schedule=anchor.schedule, at=settled)
            except Exception:
                _logger.exception("channel.schedule.pass_failed", extra={"task": task.uid})
                continue
            if due is not None and (earliest is None or due < earliest):
                earliest = due
        if after != before:
            self._anchors.replace(after)
        self._next_due = earliest

    async def _consider(
        self, task: Resource, counted_from: datetime, now: datetime
    ) -> tuple[datetime | None, datetime | None]:
        """Run or skip ``task``'s due slot. Returns when it is next due, and
        the slot settled now (``None`` when none was due)."""
        config = ScheduledTaskConfig.model_validate(task.config)
        due = next_slot(config.schedule, counted_from)
        if due is None or due > now:
            return due, None
        # The most recent slot at or before now; anything older is let go.
        slot = due
        while (following := next_slot(config.schedule, slot)) is not None and following <= now:
            slot = following
        request = RunRequest(task=task, due_at=slot, late=now - slot > _ON_TIME)
        if task.uid in self._running:
            await self._runner.skip(request, "the previous run was still going")
        elif now - slot > (CATCH_UP_WINDOW if config.catch_up else _ON_TIME):
            await self._runner.skip(request, "missed: this computer was asleep or Coffer was off")
        else:
            await self._start(request)
        return next_slot(config.schedule, slot), slot

    async def _start(self, request: RunRequest) -> ScheduledRun:
        """Start a run, marked as going until it settles. A run that could not
        even be recorded is not going."""
        uid = request.task.uid
        self._running.add(uid)
        try:
            return await self._runner.run(request)
        except BaseException:
            self._running.discard(uid)
            raise

    async def run_now(self, task: Resource) -> ScheduledRun:
        """Run ``task`` once, now, whatever its schedule (Run now)."""
        if task.uid in self._running:
            raise ValueError("the task is already running")
        return await self._start(RunRequest(task=task, due_at=self._clock(), trigger="manual"))

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
            await self._resources.set_enabled(task.uid, False, ACTOR)
            return
        if not is_repeating(config.schedule) or run.outcome != "failed":
            return
        recent = await self._runs.for_task(task.uid, limit=FAILURES_BEFORE_PAUSE)
        failed = [r for r in recent if r.outcome == "failed"]
        if len(recent) == FAILURES_BEFORE_PAUSE and len(failed) == FAILURES_BEFORE_PAUSE:
            await self._resources.set_enabled(task.uid, False, ACTOR)
