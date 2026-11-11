"""Scheduled-task routes (spec channels "Manage scheduled tasks from the
Scheduled tasks page").

What is particular to a task lives here: creating one (named after its prompt
when no name is given), its ``PROMPT.md``, the files in its folder (read-only,
as a skill's are), its run history and Run now. Editing, pausing,
renaming and removing a task are the kind-agnostic ``/api/v1/resources``
routes; the kind checks the schedule on every one of them.
"""

from __future__ import annotations

import pathlib
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from coffer.application.skill import file_ops
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.channel.scheduled_task import ScheduledTaskConfig
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.skill_file_routes import (
    SkillFileContentOut,
    SkillFileTreeOut,
    _content_out,
    _node_to_out,
)

if TYPE_CHECKING:
    from coffer.application.channel.schedule.scheduler import TaskScheduler
    from coffer.application.channel.schedule.tasks import TaskService, TaskView

router = APIRouter(prefix="/api/v1/scheduled-tasks", dependencies=[Depends(require_token)])


class _Wired:
    tasks: Any = None
    scheduler: Any = None
    reads: Any = None


_WIRED = _Wired()


def set_schedule_services(*, tasks: TaskService, scheduler: TaskScheduler, reads: Any) -> None:
    _WIRED.tasks, _WIRED.scheduler, _WIRED.reads = tasks, scheduler, reads


def _tasks() -> TaskService:
    if _WIRED.tasks is None:
        raise RuntimeError("scheduled tasks not initialised")
    return _WIRED.tasks  # type: ignore[no-any-return]


class RunConversationOut(BaseModel):
    """The conversation a run used, as the history opens it: the agent's native
    session resumes in a terminal, where the run can be read and carried on."""

    conversation_id: str
    title: str
    agent_key: str
    #: The agent's native session; null until a turn has run on it.
    session_id: str | None
    cwd: str | None
    #: A turn is under way on it now (this run's or a later one).
    running: bool


class ScheduledRunOut(BaseModel):
    run_id: str
    task_uid: str
    task_name: str
    due_at: datetime
    started_at: datetime
    finished_at: datetime | None
    outcome: Literal["running", "done", "skipped", "failed", "stopped"]
    #: Why it was skipped or failed; ``""`` otherwise.
    reason: str
    #: Late for its slot: the Mac slept or Coffer was off.
    catch_up: bool
    trigger: Literal["schedule", "manual"]
    conversation_id: str
    #: The conversation it used, in the history only; null for a run that
    #: never started one, or whose conversation has since been removed.
    conversation: RunConversationOut | None = None


class ScheduledTaskOut(BaseModel):
    uid: str
    name: str
    description: str | None
    #: Off is paused (or a one-off that has run).
    enabled: bool
    config: ScheduledTaskConfig
    created_at: datetime
    updated_at: datetime
    last_run: ScheduledRunOut | None
    next_run: datetime | None
    running: bool
    #: The task's ``PROMPT.md``.
    prompt: str
    #: The task's own folder: its ``PROMPT.md``, and where its runs work when
    #: it names no directory.
    folder: str


class ScheduledTaskListOut(BaseModel):
    items: list[ScheduledTaskOut]


class ScheduledRunListOut(BaseModel):
    items: list[ScheduledRunOut]


class ScheduledTaskIn(BaseModel):
    #: Omitted: named after the prompt's first words.
    name: str | None = None
    description: str = ""
    #: Written to the task's ``PROMPT.md``. Older callers send it in ``config``.
    prompt: str | None = None
    config: ScheduledTaskConfig


class ScheduledTaskPromptIn(BaseModel):
    prompt: str = Field(min_length=1)


def run_out(run: ScheduledRun, conversation: RunConversationOut | None = None) -> ScheduledRunOut:
    return ScheduledRunOut(
        run_id=run.run_id,
        task_uid=run.task_uid,
        task_name=run.task_name,
        due_at=run.due_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        outcome=run.outcome,
        reason=run.reason,
        catch_up=run.catch_up,
        trigger=run.trigger,
        conversation_id=run.conversation_id,
        conversation=conversation,
    )


async def _out(view: TaskView) -> ScheduledTaskOut:
    task = view.task
    return ScheduledTaskOut(
        uid=task.uid,
        name=task.name,
        description=task.description,
        enabled=task.enabled,
        config=view.config,
        created_at=task.created_at,
        updated_at=task.updated_at,
        last_run=run_out(view.last_run) if view.last_run is not None else None,
        next_run=view.next_run,
        running=view.running,
        prompt=view.prompt,
        folder=view.folder,
    )


@router.get("", response_model=ScheduledTaskListOut)
async def list_tasks() -> ScheduledTaskListOut:
    return ScheduledTaskListOut(items=[await _out(v) for v in await _tasks().views()])


@router.post("", response_model=ScheduledTaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(body: ScheduledTaskIn, actor: str = Depends(get_actor)) -> ScheduledTaskOut:
    task = await _tasks().create(
        body.name,
        body.config.model_dump(mode="json", exclude_none=True),
        actor=actor,
        description=body.description,
        prompt=body.prompt,
    )
    return await _out(await _tasks().view(task.uid))


@router.get("/{uid}", response_model=ScheduledTaskOut)
async def get_task(uid: str) -> ScheduledTaskOut:
    return await _out(await _tasks().view(uid))


@router.put("/{uid}/prompt", response_model=ScheduledTaskOut)
async def set_task_prompt(uid: str, body: ScheduledTaskPromptIn) -> ScheduledTaskOut:
    """Replace the task's ``PROMPT.md``; the next run is given it."""
    return await _out(await _tasks().set_prompt(uid, body.prompt))


@router.get("/{uid}/files", response_model=SkillFileTreeOut)
async def list_task_files(uid: str) -> SkillFileTreeOut:
    """The task's folder as a read-only file tree."""
    folder = pathlib.Path((await _tasks().view(uid)).folder).resolve()
    return SkillFileTreeOut(root=_node_to_out(file_ops.build_file_tree(folder), folder))


@router.get("/{uid}/files/content", response_model=SkillFileContentOut)
async def read_task_file(uid: str, path: str = Query(min_length=1)) -> SkillFileContentOut:
    """One file of the task's folder; a path resolving outside it is refused."""
    folder = pathlib.Path((await _tasks().view(uid)).folder).resolve()
    try:
        result = file_ops.read_skill_file(folder, path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requested path is outside the task's folder",
        ) from exc
    except (FileNotFoundError, IsADirectoryError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"no such file in the task: {path}"
        ) from exc
    return _content_out(result, folder)


@router.get("/{uid}/runs", response_model=ScheduledRunListOut)
async def list_task_runs(
    uid: str, limit: int = Query(default=50, ge=1, le=200)
) -> ScheduledRunListOut:
    if _WIRED.reads is None:
        return ScheduledRunListOut(items=[])
    runs = await _WIRED.reads.runs_of(uid, limit)
    found = await _WIRED.reads.conversations({r.conversation_id for r in runs})
    return ScheduledRunListOut(
        items=[
            run_out(
                r,
                RunConversationOut(**found[r.conversation_id])
                if r.conversation_id in found
                else None,
            )
            for r in runs
        ]
    )


@router.post("/{uid}/run", response_model=ScheduledRunOut, status_code=status.HTTP_202_ACCEPTED)
async def run_task_now(uid: str) -> ScheduledRunOut:
    """Run the task once, now, whatever its schedule."""
    view = await _tasks().view(uid)
    try:
        return run_out(await _WIRED.scheduler.run_now(view.task))
    except ValueError as e:  # it is already running
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
