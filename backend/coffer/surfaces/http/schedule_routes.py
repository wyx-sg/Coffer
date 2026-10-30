"""Scheduled-task routes (spec channels "Manage scheduled tasks from the
Scheduled tasks page").

What is particular to a task lives here: creating one (named after its prompt
when no name is given), its run history, Run now, the chats a task may run in,
and the daily report made from its template. Editing, pausing, renaming and
removing a task are the kind-agnostic ``/api/v1/resources`` routes; the kind
checks the chat and the schedule on every one of them.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.channel.scheduled_task import ScheduledTaskConfig
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor

if TYPE_CHECKING:
    from coffer.application.channel.schedule.scheduler import TaskScheduler
    from coffer.application.channel.schedule.tasks import TaskService, TaskView

router = APIRouter(prefix="/api/v1/scheduled-tasks", dependencies=[Depends(require_token)])


class _Wired:
    tasks: Any = None
    scheduler: Any = None
    chats: Any = None


_WIRED = _Wired()


def set_schedule_services(*, tasks: TaskService, scheduler: TaskScheduler, chats: Any) -> None:
    _WIRED.tasks, _WIRED.scheduler, _WIRED.chats = tasks, scheduler, chats


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
    outcome: Literal["running", "replied", "silent", "skipped", "failed", "stopped"]
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
    #: The channel's name, as the list shows it.
    channel_name: str
    last_run: ScheduledRunOut | None
    next_run: datetime | None
    running: bool


class ScheduledTaskListOut(BaseModel):
    items: list[ScheduledTaskOut]


class ScheduledRunListOut(BaseModel):
    items: list[ScheduledRunOut]


class ScheduledTaskIn(BaseModel):
    #: Omitted: named after the prompt's first words.
    name: str | None = None
    description: str = ""
    config: ScheduledTaskConfig


class TaskChatOut(BaseModel):
    """A chat a task may run in: one the owner uses with a channel's bot."""

    channel: str
    channel_name: str
    chat_id: str
    chat_kind: Literal["direct", "group"]
    #: Who paired it (a direct chat) — Coffer keeps no group title.
    label: str


class TaskChatListOut(BaseModel):
    items: list[TaskChatOut]


class DailyReportIn(BaseModel):
    channel: str = Field(min_length=1)
    time: str = Field(default="18:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    #: The agent key that writes it; omitted, the channel's default agent.
    agent: str | None = None


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
    names = await _WIRED.chats.channel_names() if _WIRED.chats is not None else {}
    return ScheduledTaskOut(
        uid=task.uid,
        name=task.name,
        description=task.description,
        enabled=task.enabled,
        config=view.config,
        created_at=task.created_at,
        updated_at=task.updated_at,
        channel_name=names.get(view.config.chat.channel, view.config.chat.channel),
        last_run=run_out(view.last_run) if view.last_run is not None else None,
        next_run=view.next_run,
        running=view.running,
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
    )
    return await _out(await _tasks().view(task.uid))


@router.get("/chats", response_model=TaskChatListOut)
async def list_task_chats() -> TaskChatListOut:
    """The chats a new task may run in."""
    rows = await _WIRED.chats.chats() if _WIRED.chats is not None else []
    return TaskChatListOut(items=[TaskChatOut(**row) for row in rows])


@router.put("/daily-report", response_model=ScheduledTaskOut)
async def set_daily_report(
    body: DailyReportIn, actor: str = Depends(get_actor)
) -> ScheduledTaskOut:
    """Make the daily report task from its template, or move the one there is."""
    task = await _tasks().daily_report(
        channel_uid=body.channel, time=body.time, agent=body.agent, actor=actor
    )
    return await _out(await _tasks().view(task.uid))


@router.get("/{uid}", response_model=ScheduledTaskOut)
async def get_task(uid: str) -> ScheduledTaskOut:
    return await _out(await _tasks().view(uid))


@router.get("/{uid}/runs", response_model=ScheduledRunListOut)
async def list_task_runs(
    uid: str, limit: int = Query(default=50, ge=1, le=200)
) -> ScheduledRunListOut:
    if _WIRED.chats is None:
        return ScheduledRunListOut(items=[])
    runs = await _WIRED.chats.runs_of(uid, limit)
    found = await _WIRED.chats.conversations({r.conversation_id for r in runs})
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
