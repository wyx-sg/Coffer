"""Scheduled-task composition (spec channels "Keep scheduled tasks as
machine-local resources") — called from ``wire_channel_kind``.

A scheduled task is a turn Coffer starts in a paired chat (ADR
scheduled-tasks-are-turns-coffer-starts-in-a-chat), so it is wired inside the
channel kind's composition, against the same inbound processor, peers and
threads. What this root adds beyond the channel package is what only a root
may see: the agent kind's sessions (the daily report's material), the chat
platform's conversation listing, and the gateway's turn tokens (which turn a
tool call came from).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from coffer.application.agent.native_session_service import NativeSessionService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.channel.ephemeral import safe_send
from coffer.application.channel.inbound import InboundProcessor
from coffer.application.channel.schedule.kind import KIND, make_scheduled_task_kind
from coffer.application.channel.schedule.material import (
    WaitingTask,
    channel_day,
    day_conversations,
)
from coffer.application.channel.schedule.ports import SessionTail
from coffer.application.channel.schedule.runner import TaskRunner
from coffer.application.channel.schedule.scheduler import TaskScheduler
from coffer.application.channel.schedule.tasks import TaskService
from coffer.application.channel.schedule.tools import ScheduleTools, schedule_tools
from coffer.application.channel.status_tasks import WaitingTaskLine
from coffer.application.channel.store_ports import (
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
)
from coffer.application.chat import turn_tokens
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_state import is_running
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.domain.agent.config import AgentConfig
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.channel.scheduled_task import ScheduledTaskConfig
from coffer.domain.chat.errors import ConversationNotFound
from coffer.domain.features import SCHEDULED_TASKS
from coffer.domain.resource import Resource
from coffer.infrastructure.channel.persistence import ScheduledRunRepo
from coffer.surfaces.http.chat_wiring import ChatWiring
from coffer.surfaces.http.event_wiring import EventStream
from coffer.surfaces.http.feature_dependencies import get_feature_service_optional
from coffer.surfaces.http.schedule_routes import set_schedule_services

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["ScheduleWiring", "wire_scheduled_tasks"]

#: How many conversations one listing page reads while gathering material.
_PAGE = 50


@dataclass
class ScheduleWiring:
    tasks: TaskService
    scheduler: TaskScheduler
    runs: ScheduledRunRepo
    resources: ResourceService

    async def forget_channel(self, channel_uid: str) -> None:
        """A channel is removed: its tasks and their history go with it."""
        for task in await self.resources.list(kind=KIND):
            if (task.config.get("chat") or {}).get("channel") == channel_uid:
                await self.resources.delete(task.uid, "coffer:channel-removed")
        await self.runs.delete_for_channel(channel_uid)


class _SessionTails:
    """``SessionTailPort`` over the agent kind's native sessions: a
    conversation names an agent type, the sessions service an agent uid."""

    def __init__(self, resources: ResourceService, sessions: NativeSessionService) -> None:
        self._resources = resources
        self._sessions = sessions

    async def tail(self, agent_key: str, session_id: str, cwd: str | None) -> SessionTail:
        for agent in await self._resources.list(kind="agent"):
            try:
                cfg = AgentConfig.model_validate(agent.config)
            except ValueError:
                continue
            if cfg.type.value == agent_key:
                asked, answered = await self._sessions.tail(agent.uid, session_id, cwd)
                return SessionTail(asked=asked, answered=answered)
        return SessionTail(asked="", answered="")


class _GatedChatTasks:
    """``ChatTasksPort`` that lists and cancels nothing while the
    ``scheduled_tasks`` feature is off (spec experimental-features "Close every
    surface of a switched-off feature")."""

    def __init__(self, tasks: TaskService, enabled: Callable[[], bool]) -> None:
        self._tasks = tasks
        self._enabled = enabled

    async def waiting(
        self, channel_uid: str, chat_id: str, conversation_thread_id: str
    ) -> list[WaitingTaskLine]:
        if not self._enabled():
            return []
        return await self._tasks.waiting(channel_uid, chat_id, conversation_thread_id)

    async def cancel(self, uid: str, *, actor: str) -> str | None:
        if not self._enabled():
            return None
        return await self._tasks.cancel(uid, actor=actor)


class _Chats:
    """What the page reads beside the tasks: the chats a task may run in, the
    channels' names, a task's run history."""

    def __init__(
        self,
        resources: ResourceService,
        peers: ChannelPeerRepoPort,
        threads: ChannelThreadConversationRepoPort,
        runs: ScheduledRunRepo,
        chat: ChatService,
    ) -> None:
        self._chat = chat
        self._resources = resources
        self._peers = peers
        self._threads = threads
        self._runs = runs

    async def channel_names(self) -> dict[str, str]:
        return {r.uid: r.name for r in await self._resources.list(kind="channel")}

    async def chats(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for channel in await self._resources.list(kind="channel"):
            for peer in await self._peers.list_by_resource(channel.uid):
                row = await self._threads.get(channel.uid, peer.chat_id, "")
                kind = row.chat_kind if row is not None and row.chat_kind else "direct"
                rows.append(
                    {
                        "channel": channel.uid,
                        "channel_name": channel.name,
                        "chat_id": peer.chat_id,
                        "chat_kind": "group" if kind == "group" else "direct",
                        "label": peer.display_name,
                    }
                )
        return rows

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


def wire_scheduled_tasks(
    app: FastAPI,
    *,
    resource_svc: ResourceService,
    sm: async_sessionmaker[AsyncSession],
    peers: ChannelPeerRepoPort,
    threads: ChannelThreadConversationRepoPort,
    processor: InboundProcessor,
    chat: ChatWiring,
    sessions: NativeSessionService | None,
    builtin_tools: BuiltinToolRegistry,
    events: EventStream,
) -> ScheduleWiring:
    runs = ScheduledRunRepo(sm)
    tails = _SessionTails(resource_svc, sessions) if sessions is not None else None
    chats = _Chats(resource_svc, peers, threads, runs, chat.chat_service)
    holder: dict[str, TaskService] = {}

    async def material(task: Resource, now: datetime) -> str:
        """The day's channel conversations, for a task that asks for them."""
        since = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        today = await runs.since(since)
        # The report's own runs are not conversations to report on.
        exclude = {r.conversation_id for r in today if r.task_uid == task.uid}

        async def page(cursor: str | None) -> tuple[list[Any], str | None]:
            got = await chat.chat_service.page_conversations(limit=_PAGE, cursor=cursor)
            return list(got.items), got.next_cursor

        names = await chats.channel_names()
        conversations, total = await day_conversations(
            since=since,
            page=page,
            threads=threads,
            tails=tails,
            channel_names=names,
            exclude=exclude,
        )
        waiting = [
            WaitingTask(
                name=v.task.name,
                next_run=v.next_run,
                where=names.get(v.config.chat.channel, v.config.chat.channel),
            )
            for v in (await holder["tasks"].views() if "tasks" in holder else [])
            if v.next_run is not None and v.task.uid != task.uid
        ]
        return channel_day(
            since=since,
            conversations=conversations,
            total=total,
            runs=[r for r in today if r.task_uid != task.uid],
            waiting=waiting,
        )

    async def notify(task: Resource, text: str) -> None:
        config = ScheduledTaskConfig.model_validate(task.config)
        binding = processor.binding(config.chat.channel)
        if binding is not None:
            await safe_send(
                binding,
                config.chat.chat_id,
                text,
                thread_id=config.chat.thread_id,
                chat_kind=config.chat.chat_kind,
            )

    runner = TaskRunner(
        runs=runs,
        binding=processor.binding,
        peers=peers,
        threads=threads,
        conversations=chat.chat_service,
        driver=lambda: processor.turn_driver,
        material=material,
    )
    features = get_feature_service_optional()

    def enabled() -> bool:
        # An app assembled without ``create_app`` has no feature service;
        # there the tasks run, as every gate there lets everything through.
        return features is None or features.is_enabled(SCHEDULED_TASKS)

    scheduler = TaskScheduler(
        resources=resource_svc, runs=runs, runner=runner, notify=notify, enabled=enabled
    )
    tasks = TaskService(
        resources=resource_svc,
        runs=runs,
        peers=peers,
        next_run=scheduler.next_run,
        is_running=scheduler.is_running,
    )
    holder["tasks"] = tasks

    async def channel_uids() -> set[str]:
        return {r.uid for r in await resource_svc.list(kind="channel")}

    async def paired(channel_uid: str, chat_id: str) -> bool:
        return await peers.get_by_chat(channel_uid, chat_id) is not None

    app.state.kinds[KIND] = make_scheduled_task_kind(channels=channel_uids, paired=paired)
    # `/status` lists and cancels what waits in its conversation, while the
    # feature is on.
    processor.commands.scheduled = _GatedChatTasks(tasks, enabled)
    builtin_tools_list = schedule_tools(
        ScheduleTools(
            tasks=tasks, resources=resource_svc, conversation_of=turn_tokens.conversation_of
        )
    )
    for tool in builtin_tools_list:
        builtin_tools.register(tool)
    set_schedule_services(tasks=tasks, scheduler=scheduler, chats=chats)
    # A task created, edited, paused or removed (here, on the page, by sync or
    # by hand) brings the next pass forward.
    events.late_sinks.append(scheduler.on_changed)
    # Switching the feature on brings the first pass forward.
    if features is not None:
        features.subscribe(lambda key, _on: scheduler.poke() if key == SCHEDULED_TASKS else None)
    spawn_restarting(scheduler.serve, name="scheduled-tasks")
    return ScheduleWiring(tasks=tasks, scheduler=scheduler, runs=runs, resources=resource_svc)
