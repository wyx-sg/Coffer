"""Creating and reading scheduled tasks (spec channels "Keep scheduled tasks as
machine-local resources").

The owner's page and CLI create a task here; editing, pausing and removing are
the kind-agnostic resource routes, checked by the kind.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from coffer.application.channel.schedule.kind import KIND
from coffer.application.channel.schedule.ports import ScheduledRunRepoPort, TaskFolderPort
from coffer.application.resource_service import ResourceService
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.channel.scheduled_task import (
    ScheduledTaskConfig,
    clean_prompt,
    is_retired_follow_up,
)
from coffer.domain.errors import ConfigValidationError, ResourceNotFound
from coffer.domain.resource import FREE_NAME_MAX_LEN, Resource, same_free_name

__all__ = ["TaskService", "TaskView"]

#: Who the audit log names for removing what an older Coffer left behind.
_UPGRADE_ACTOR = "coffer:upgrade"


@dataclass(frozen=True)
class TaskView:
    """A task as the list shows it."""

    task: Resource
    config: ScheduledTaskConfig
    last_run: ScheduledRun | None
    next_run: datetime | None
    running: bool
    #: The task's ``PROMPT.md``; ``""`` when the file is missing.
    prompt: str
    #: The task's own folder.
    folder: str


def _name_from(text: str) -> str:
    first = " ".join(text.split())
    return first if len(first) <= 60 else first[:59] + "…"


class TaskService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        runs: ScheduledRunRepoPort,
        next_run: Callable[[Resource], Any],
        is_running: Callable[[str], bool],
        folders: TaskFolderPort,
    ) -> None:
        self._folders = folders
        self._resources = resources
        self._runs = runs
        self._next_run = next_run
        self._is_running = is_running

    # -- reading --------------------------------------------------------------

    async def views(self) -> list[TaskView]:
        tasks = await self._resources.list(kind=KIND)
        last = await self._runs.latest_for([t.uid for t in tasks])
        views = [await self._view(t, last.get(t.uid)) for t in tasks]
        far = datetime.max.replace(tzinfo=UTC)
        return sorted(views, key=lambda v: (v.next_run or far, v.task.name.casefold()))

    async def view(self, uid: str) -> TaskView:
        task = await self._resources.get(uid)
        if task.kind != KIND:
            raise ResourceNotFound(uid)
        last = await self._runs.latest_for([uid])
        return await self._view(task, last.get(uid))

    async def _view(self, task: Resource, last: ScheduledRun | None) -> TaskView:
        return TaskView(
            task=task,
            config=ScheduledTaskConfig.model_validate(task.config),
            last_run=last,
            next_run=await self._next_run(task),
            running=self._is_running(task.uid),
            prompt=self._folders.read_prompt(task.uid) or "",
            folder=self._folders.path(task.uid),
        )

    # -- writing --------------------------------------------------------------

    async def create(
        self,
        name: str | None,
        config: dict[str, Any],
        *,
        actor: str,
        description: str = "",
        prompt: str | None = None,
    ) -> Resource:
        """Register the task and write its ``PROMPT.md``. The prompt comes as
        ``prompt`` or, as older callers send it, inside ``config``."""
        rest = {k: v for k, v in config.items() if k != "prompt"}
        if prompt is None:
            prompt = config.get("prompt")
        try:
            parsed = ScheduledTaskConfig.model_validate(rest)
            text = clean_prompt(prompt if isinstance(prompt, str) else "")
        except (ValidationError, ValueError) as e:
            raise ConfigValidationError(str(e)) from e
        task = await self._resources.register(
            KIND,
            await self._free_name(name or _name_from(text)),
            parsed.model_dump(mode="json", exclude_none=True),
            actor,
            description or None,
        )
        self._folders.write_prompt(task.uid, text)
        return task

    async def set_prompt(self, uid: str, prompt: str) -> TaskView:
        """Replace the task's ``PROMPT.md``; the next run is given it."""
        view = await self.view(uid)
        try:
            text = clean_prompt(prompt)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e
        self._folders.write_prompt(uid, text)
        return await self._view(view.task, view.last_run)

    async def move_prompts_to_files(self) -> int:
        """Move the prompt a task file written before 2026-11-11 carries into
        the task's ``PROMPT.md`` (kept when one is already there)."""
        moved = 0
        for task in await self._resources.list(kind=KIND):
            prompt = task.config.get("prompt")
            if prompt is None:
                continue
            if self._folders.read_prompt(task.uid) is None and str(prompt).strip():
                self._folders.write_prompt(task.uid, str(prompt).strip())
            rest = {k: v for k, v in task.config.items() if k != "prompt"}
            config = ScheduledTaskConfig.model_validate(rest)
            await self._resources.update_config(
                task.uid, config.model_dump(mode="json", exclude_none=True), _UPGRADE_ACTOR
            )
            moved += 1
        return moved

    async def drop_retired_follow_ups(self) -> int:
        """Remove the follow-ups an older Coffer let agents book in a chat
        (2026-11-06): without their chat they mean nothing. Their runs stay."""
        dropped = 0
        for task in await self._resources.list(kind=KIND):
            if is_retired_follow_up(task.config):
                await self._resources.delete(task.uid, _UPGRADE_ACTOR)
                dropped += 1
        return dropped

    async def _free_name(self, wanted: str) -> str:
        """``wanted``, or ``wanted (2)`` … when another task has that name."""
        base = wanted.strip()[: FREE_NAME_MAX_LEN - 6] or "Scheduled task"
        taken = [t.name for t in await self._resources.list(kind=KIND)]
        name, n = base, 1
        while any(same_free_name(name, other) for other in taken):
            n += 1
            name = f"{base} ({n})"
        return name
