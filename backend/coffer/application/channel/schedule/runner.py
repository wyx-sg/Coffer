"""One run of a scheduled task: from the history row to a turn in a fresh
conversation of its own (spec scheduled-tasks "Run a scheduled task in a fresh
conversation of its own").

A run opens a new conversation on the task's agent and model, in the folder
the task names (its own when it names none), and hands it the task's ``PROMPT.md``,
the way the owner would on the Conversations page; the answer stays in that
conversation, and the history row is how the owner finds it (ADR
automation-is-a-scheduled-prompt). What a run adds is its row, opened
``running`` before anything else and closed with how the turn ended.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from coffer.application.channel.schedule.message import run_message
from coffer.application.channel.schedule.ports import (
    FreshTurnPort,
    ScheduledRunRepoPort,
    TaskFolderPort,
)
from coffer.domain.channel.scheduled_run import RunOutcome, ScheduledRun
from coffer.domain.channel.scheduled_task import PROMPT_FILE, ScheduledTaskConfig
from coffer.domain.errors import CofferError
from coffer.domain.resource import Resource

__all__ = ["RunRequest", "TaskRunner"]

_logger = logging.getLogger(__name__)

#: Told once a run has ended, however it ended, with its final row.
OnSettled = Callable[[Resource, ScheduledRun], Awaitable[None]]


@dataclass(frozen=True)
class RunRequest:
    task: Resource
    due_at: datetime
    late: bool = False
    trigger: str = "schedule"


class TaskRunner:
    def __init__(
        self,
        *,
        runs: ScheduledRunRepoPort,
        fresh: FreshTurnPort,
        folders: TaskFolderPort,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._runs = runs
        self._fresh = fresh
        self._folders = folders
        self._clock = clock
        self.on_settled: OnSettled | None = None

    async def skip(self, request: RunRequest, reason: str) -> ScheduledRun:
        """Record a slot that will not run, and why."""
        run = self._row(request, outcome="skipped", reason=reason)
        await self._runs.add(run)
        await self._settled(request.task, run)
        return run

    async def run(self, request: RunRequest) -> ScheduledRun:
        """Start the run; it ends when its turn does (``on_settled`` is told)."""
        task = request.task
        run = self._row(request, outcome="running")
        await self._runs.add(run)
        try:
            return await self._start(request, ScheduledTaskConfig.model_validate(task.config), run)
        except Exception as exc:  # a run must end, whatever stopped it
            _logger.exception("channel.schedule.run_failed", extra={"task": task.uid})
            return await self._fail(task, run, f"Coffer could not start it ({type(exc).__name__})")

    async def _start(
        self, request: RunRequest, config: ScheduledTaskConfig, run: ScheduledRun
    ) -> ScheduledRun:
        task = request.task

        async def on_end(outcome: RunOutcome, reason: str) -> None:
            await self._end(task, run, outcome, reason)

        prompt = (self._folders.read_prompt(task.uid) or "").strip()
        if not prompt:
            # A task without one cannot be resumed; this is a file emptied by hand.
            return await self._fail(task, run, f"{PROMPT_FILE} is missing or empty")
        text = run_message(
            prompt=prompt,
            due_at=request.due_at,
            now=self._clock(),
            late=request.late,
            manual=request.trigger == "manual",
        )
        if config.cwd is not None and not self._folders.exists(config.cwd):
            return await self._fail(task, run, f"its folder {config.cwd} does not exist")
        try:
            conversation_id = await self._fresh.start(
                agent=config.agent,
                model=config.model,
                cwd=config.cwd or self._folders.path(task.uid),
                title=task.name,
                text=text,
                on_end=on_end,
            )
        except (CofferError, ValueError) as e:
            return await self._fail(task, run, str(e))
        await self._runs.note_conversation(run.run_id, conversation_id)
        return replace(run, conversation_id=conversation_id)

    def _row(self, request: RunRequest, *, outcome: RunOutcome, reason: str = "") -> ScheduledRun:
        now = self._clock()
        return ScheduledRun(
            run_id=uuid.uuid4().hex,
            task_uid=request.task.uid,
            task_name=request.task.name,
            due_at=request.due_at,
            catch_up=request.late,
            trigger="manual" if request.trigger == "manual" else "schedule",
            started_at=now,
            outcome=outcome,
            reason=reason,
            finished_at=now if outcome != "running" else None,
        )

    async def _fail(self, task: Resource, run: ScheduledRun, reason: str) -> ScheduledRun:
        return await self._end(task, run, "failed", reason)

    async def _end(
        self, task: Resource, run: ScheduledRun, outcome: RunOutcome, reason: str
    ) -> ScheduledRun:
        finished = self._clock()
        ended = replace(run, outcome=outcome, reason=reason, finished_at=finished)
        try:
            await self._runs.finish(
                run.run_id, outcome=outcome, reason=reason, finished_at=finished
            )
        finally:
            # Told even when the row could not be closed: the task is no longer
            # running, and the next start closes a row left open.
            await self._settled(task, ended)
        return ended

    async def _settled(self, task: Resource, run: ScheduledRun) -> None:
        if self.on_settled is not None:
            try:
                await self.on_settled(task, run)
            except Exception:
                _logger.exception("channel.schedule.settle_failed", extra={"task": task.uid})
