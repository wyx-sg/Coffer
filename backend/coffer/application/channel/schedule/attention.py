"""What about the scheduled tasks needs a person (the Overview list; spec
scheduled-tasks "Tell the owner when a task was paused for failing").

One signal: ``scheduled_task_paused_failing`` — a repeating task that is
switched off and whose last runs all failed, which is how the scheduler leaves
a task it paused. A failed run cannot tell the owner itself (its agent is what
failed), so this is the one thing about a task Coffer reports. It clears when
the task is resumed or removed; a task the owner paused while it was failing
reads the same, and can be ignored like any item.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.application.channel.schedule.kind import KIND
from coffer.application.channel.schedule.scheduler import FAILURES_BEFORE_PAUSE
from coffer.domain.channel.schedule import is_repeating
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.channel.scheduled_task import ScheduledTaskConfig
from coffer.domain.features import SCHEDULED_TASKS
from coffer.domain.resource import Resource

__all__ = ["ScheduledTaskAttentionSource"]


class _TasksPort(Protocol):
    async def list(
        self, kind: str | None = None, enabled: bool | None = None
    ) -> Sequence[Resource]: ...


class _RunsPort(Protocol):
    async def for_task(self, task_uid: str, *, limit: int = 50) -> list[ScheduledRun]: ...


class ScheduledTaskAttentionSource:
    name = KIND
    feature: str | None = SCHEDULED_TASKS

    def __init__(self, *, resources: _TasksPort, runs: _RunsPort) -> None:
        self._resources = resources
        self._runs = runs

    async def items(self) -> Sequence[AttentionItem]:
        out: list[AttentionItem] = []
        for task in await self._resources.list(kind=KIND, enabled=False):
            if not is_repeating(ScheduledTaskConfig.model_validate(task.config).schedule):
                continue
            recent = await self._runs.for_task(task.uid, limit=FAILURES_BEFORE_PAUSE)
            if len(recent) < FAILURES_BEFORE_PAUSE or any(r.outcome != "failed" for r in recent):
                continue
            last = recent[0]
            reason = f"Paused after {FAILURES_BEFORE_PAUSE} runs in a row failed"
            reason += f": {last.reason}" if last.reason else "."
            out.append(
                AttentionItem(
                    kind=KIND,
                    uid=task.uid,
                    title=task.name,
                    reason_code="scheduled_task_paused_failing",
                    reason=reason,
                    severity=Severity.WARNING,
                    since=last.finished_at or last.started_at,
                    action=AttentionAction(
                        verb="review", method="GET", path=f"/api/v1/scheduled-tasks/{task.uid}"
                    ),
                )
            )
        return out
