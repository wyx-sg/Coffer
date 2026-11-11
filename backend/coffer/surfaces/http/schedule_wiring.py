"""Scheduled-task composition (spec channels "Keep scheduled tasks as
machine-local resources") — called from ``create_app`` after the chat platform.

A run is a turn in a new conversation, so what this root adds is the chat
platform: its conversations (where each run happens and its history opens)
and its orchestrator (which runs the turn).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from coffer.application.channel.schedule.kind import KIND, make_scheduled_task_kind
from coffer.application.channel.schedule.runner import TaskRunner
from coffer.application.channel.schedule.scheduler import TaskScheduler
from coffer.application.channel.schedule.tasks import TaskService
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.chat.turn_state import is_running
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import spawn, spawn_restarting
from coffer.domain.channel.scheduled_run import RunOutcome, ScheduledRun
from coffer.domain.chat.errors import ConversationNotFound
from coffer.domain.chat.events import AgentEvent, TurnDone, TurnError
from coffer.domain.features import SCHEDULED_TASKS
from coffer.infrastructure.channel.persistence import ScheduledRunRepo
from coffer.infrastructure.channel.task_folders import TaskFolders
from coffer.surfaces.http.chat_wiring import ChatWiring
from coffer.surfaces.http.event_wiring import EventStream
from coffer.surfaces.http.feature_dependencies import get_feature_service_optional
from coffer.surfaces.http.schedule_routes import set_schedule_services

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["FreshTurns", "wire_scheduled_tasks"]


class FreshTurns:
    """``FreshTurnPort`` over the chat platform: every run is a new
    conversation of its own, on the agent's orchestrator like any conversation
    the owner opens on the Conversations page."""

    def __init__(self, chat_service: ChatService, orchestrator: TurnOrchestrator) -> None:
        self._chat_service = chat_service
        self._orchestrator = orchestrator

    async def start(
        self,
        *,
        agent: str,
        model: str | None,
        cwd: str,
        title: str,
        text: str,
        on_end: Callable[[RunOutcome, str], Awaitable[None]],
    ) -> str:
        config: dict[str, Any] = {"cwd": cwd}
        if model:
            config["model"] = model
        conv = await self._chat_service.create_conversation(agent_key=agent, agent_config=config)

        def sink(queue: asyncio.Queue[AgentEvent | None]) -> None:
            spawn(_settle(queue, on_end), name="channel.schedule.fresh_settle")

        await self._orchestrator.enqueue_message(conv.id, text, title_hint=title, on_start=sink)
        return str(conv.id)


async def _settle(
    queue: asyncio.Queue[AgentEvent | None],
    on_end: Callable[[RunOutcome, str], Awaitable[None]],
) -> None:
    """Read the turn's events to its end and tell the run how it went."""
    outcome: RunOutcome = "stopped"
    reason = "the turn ended before it finished"
    while (event := await queue.get()) is not None:
        if isinstance(event, TurnDone):
            outcome, reason = "done", ""
        elif isinstance(event, TurnError):
            outcome, reason = "failed", event.message
    await on_end(outcome, reason)


class _Reads:
    """What the page reads beside the tasks: a task's run history and the
    conversations its runs used."""

    def __init__(self, runs: ScheduledRunRepo, chat: ChatService) -> None:
        self._runs = runs
        self._chat = chat

    async def runs_of(self, task_uid: str, limit: int) -> list[ScheduledRun]:
        return await self._runs.for_task(task_uid, limit=limit)

    async def conversations(self, ids: set[str]) -> dict[str, dict[str, Any]]:
        """The conversations runs used, by id, as the history opens them; one
        removed since (or a run that started none) is absent."""
        found: dict[str, dict[str, Any]] = {}
        for cid in ids - {""}:
            try:
                conv = await self._chat.get_conversation(cid)
            except ConversationNotFound:
                continue
            found[cid] = {
                "conversation_id": conv.id,
                "title": conv.title,
                "agent_key": conv.agent_key,
                "session_id": conv.agent_config.session_id,
                "cwd": conv.agent_config.cwd,
                "running": is_running(conv.id),
            }
        return found


async def wire_scheduled_tasks(
    app: FastAPI,
    *,
    resource_svc: ResourceService,
    sm: async_sessionmaker[AsyncSession],
    chat: ChatWiring,
    events: EventStream,
) -> None:
    runs = ScheduledRunRepo(sm)
    folders = TaskFolders()
    runner = TaskRunner(
        runs=runs, fresh=FreshTurns(chat.chat_service, chat.orchestrator), folders=folders
    )
    features = get_feature_service_optional()

    def enabled() -> bool:
        # An app assembled without ``create_app`` has no feature service;
        # there the tasks run, as every gate there lets everything through.
        return features is None or features.is_enabled(SCHEDULED_TASKS)

    scheduler = TaskScheduler(resources=resource_svc, runs=runs, runner=runner, enabled=enabled)
    tasks = TaskService(
        resources=resource_svc,
        runs=runs,
        next_run=scheduler.next_run,
        is_running=scheduler.is_running,
        folders=folders,
    )
    app.state.kinds[KIND] = make_scheduled_task_kind()
    # Follow-ups an older Coffer let agents book have no chat to run in now.
    await tasks.drop_retired_follow_ups()
    # A task written before 2026-11-11 carries its prompt in its file.
    await tasks.move_prompts_to_files()
    set_schedule_services(tasks=tasks, scheduler=scheduler, reads=_Reads(runs, chat.chat_service))
    # A task created, edited, paused or removed (here, on the page, by sync or
    # by hand) brings the next pass forward.
    events.late_sinks.append(scheduler.on_changed)
    # Switching the feature on brings the first pass forward.
    if features is not None:
        features.subscribe(lambda key, _on: scheduler.poke() if key == SCHEDULED_TASKS else None)
    spawn_restarting(scheduler.serve, name="scheduled-tasks")
