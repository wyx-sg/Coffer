"""Creating and reading scheduled tasks: the one place that knows the rules a
task must keep beyond its own shape (spec channels "Keep scheduled tasks as
machine-local resources" and "Let an agent book a follow-up in the thread it is
answering").

Three ways in, one service: the owner's page and CLI (:meth:`TaskService.create`),
an agent inside a turn (:meth:`TaskService.book` — a follow-up in its own
thread, or, when the owner asked for it there, any task), and the Channels
page's daily report (:meth:`TaskService.daily_report`, a task made from a
template). The kind checks on every write that the chat is one its channel
has paired; a follow-up also keeps the per-thread and per-chain limits here.
Editing, pausing and removing are the kind-agnostic resource routes.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from coffer.application.channel.schedule.kind import KIND
from coffer.application.channel.schedule.ports import ScheduledRunRepoPort
from coffer.application.channel.status_tasks import WaitingTaskLine
from coffer.application.channel.store_ports import ChannelPeerRepoPort
from coffer.application.channel.turn_origin import TurnOrigin
from coffer.application.resource_service import ResourceService
from coffer.domain.channel.schedule import DailySchedule, OnceSchedule
from coffer.domain.channel.scheduled_run import ScheduledRun
from coffer.domain.channel.scheduled_task import (
    CHAIN_MAX_RUNS,
    CHAIN_MAX_SPAN,
    FOLLOW_UP_MAX_AHEAD,
    FOLLOW_UP_MIN_AHEAD,
    FOLLOW_UPS_PER_THREAD,
    MATERIAL_CHANNEL_DAY,
    TEMPLATE_DAILY_REPORT,
    ScheduledTaskConfig,
    TaskChat,
    TaskMention,
)
from coffer.domain.errors import ConfigValidationError, ResourceNotFound
from coffer.domain.resource import FREE_NAME_MAX_LEN, Resource, same_free_name

__all__ = ["DAILY_REPORT_PROMPT", "TaskService", "TaskView"]

#: What the daily report asks the agent, until the owner rewrites it.
DAILY_REPORT_PROMPT = (
    "Write today's report for the owner from the material below: one short "
    "message they can read on a phone. Lead with what needs them (open questions, "
    "failures, follow-ups still waiting), then what was settled today, most "
    "important first, one line each. Group by chat only when it helps. Leave out "
    "small talk and anything that needs no one."
)


@dataclass(frozen=True)
class TaskView:
    """A task as the list shows it."""

    task: Resource
    config: ScheduledTaskConfig
    last_run: ScheduledRun | None
    next_run: datetime | None
    running: bool


def _name_from(text: str) -> str:
    first = " ".join(text.split())
    return first if len(first) <= 60 else first[:59] + "…"


class TaskService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        runs: ScheduledRunRepoPort,
        peers: ChannelPeerRepoPort,
        next_run: Callable[[Resource], Any],
        is_running: Callable[[str], bool],
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._resources = resources
        self._runs = runs
        self._peers = peers
        self._next_run = next_run
        self._is_running = is_running
        self._clock = clock

    # -- reading --------------------------------------------------------------

    async def views(self) -> list[TaskView]:
        tasks = await self._resources.list(kind=KIND)
        last = await self._runs.latest_for([t.uid for t in tasks])
        views = [
            TaskView(
                task=t,
                config=ScheduledTaskConfig.model_validate(t.config),
                last_run=last.get(t.uid),
                next_run=await self._next_run(t),
                running=self._is_running(t.uid),
            )
            for t in tasks
        ]
        far = datetime.max.replace(tzinfo=UTC)
        return sorted(views, key=lambda v: (v.next_run or far, v.task.name.casefold()))

    async def view(self, uid: str) -> TaskView:
        task = await self._resources.get(uid)
        if task.kind != KIND:
            raise ResourceNotFound(uid)
        last = await self._runs.latest_for([uid])
        return TaskView(
            task=task,
            config=ScheduledTaskConfig.model_validate(task.config),
            last_run=last.get(uid),
            next_run=await self._next_run(task),
            running=self._is_running(uid),
        )

    async def waiting_in(self, channel_uid: str, chat_id: str, thread: str) -> list[TaskView]:
        """The enabled tasks of one chat thread, soonest first (``/status``)."""
        out = []
        for view in await self.views():
            chat = view.config.chat
            if (
                view.task.enabled
                and chat.channel == channel_uid
                and chat.chat_id == chat_id
                and chat.conversation_thread_id == thread
            ):
                out.append(view)
        return out

    async def waiting(
        self, channel_uid: str, chat_id: str, conversation_thread_id: str
    ) -> list[WaitingTaskLine]:
        """``ChatTasksPort``: what `/status` lists."""
        return [
            WaitingTaskLine(uid=v.task.uid, name=v.task.name, next_run=v.next_run)
            for v in await self.waiting_in(channel_uid, chat_id, conversation_thread_id)
        ]

    async def cancel(self, uid: str, *, actor: str) -> str | None:
        """``ChatTasksPort``: remove a task, returning its name."""
        try:
            task = await self._resources.get(uid)
        except ResourceNotFound:
            return None
        if task.kind != KIND:
            return None
        await self._resources.delete(uid, actor)
        return task.name

    # -- writing --------------------------------------------------------------

    async def create(
        self, name: str | None, config: dict[str, Any], *, actor: str, description: str = ""
    ) -> Resource:
        try:
            parsed = ScheduledTaskConfig.model_validate(config)
        except ValidationError as e:
            raise ConfigValidationError(str(e)) from e
        return await self._resources.register(
            KIND,
            await self._free_name(name or _name_from(parsed.prompt)),
            parsed.model_dump(mode="json", exclude_none=True),
            actor,
            description or None,
        )

    async def book(
        self,
        origin: TurnOrigin,
        *,
        prompt: str,
        at: datetime,
        repeat: dict[str, Any] | None,
        fresh: bool,
        name: str | None,
        actor: str,
    ) -> Resource:
        """A task an agent sets up from inside a turn. Without ``repeat`` and
        ``fresh`` it is a follow-up in this very thread, with its limits; with
        either it is a task the owner asked for there."""
        if not origin.asker_is_owner:
            raise ConfigValidationError(
                "only the bot's owners can have it schedule anything; answer this person now"
            )
        if origin.task_uid and origin.task_repeats:
            raise ConfigValidationError(
                "a run of a repeating scheduled task cannot schedule more tasks"
            )
        chat = TaskChat(
            channel=origin.channel_uid,
            chat_id=origin.chat_id,
            chat_kind="group" if origin.chat_kind == "group" else "direct",
            thread_id=origin.thread_id,
            conversation_thread_id=origin.conversation_thread_id,
        )
        mention = (
            TaskMention(
                user_id=origin.mention_user_id,
                email=origin.mention_user_email,
                name=origin.mention_user_name,
            )
            if origin.mention_user_id or origin.mention_user_email or origin.mention_user_name
            else None
        )
        if repeat is not None or fresh:
            config: dict[str, Any] = {
                "schedule": repeat or OnceSchedule(at=at).model_dump(mode="json"),
                "prompt": prompt,
                "chat": chat.model_dump(),
                "session": "fresh" if fresh else "continue",
                "origin": "owner",
            }
            if mention is not None:
                config["mention"] = mention.model_dump()
            return await self.create(name, config, actor=actor)
        now = self._clock()
        await self._check_follow_up(origin, chat, at=at, now=now)
        started = origin.chain_started_at or now
        index = origin.chain_index + 1 if origin.task_uid else 1
        follow_up: dict[str, Any] = {
            "schedule": OnceSchedule(at=at).model_dump(mode="json"),
            "prompt": prompt,
            "chat": chat.model_dump(),
            "session": "continue",
            "origin": "agent",
            "chain_started_at": started.isoformat(),
            "chain_index": index,
        }
        if mention is not None:
            follow_up["mention"] = mention.model_dump()
        return await self.create(name, follow_up, actor=actor)

    async def daily_report(
        self, *, channel_uid: str, time: str, actor: str, agent: str | None = None
    ) -> Resource:
        """Make the daily report task, or point the existing one at ``time``."""
        owner = await self._peers.owner_peer(channel_uid)
        if owner is None:
            raise ConfigValidationError("pair the channel with its owner first")
        schedule = DailySchedule(time=time).model_dump()
        for existing in await self._resources.list(kind=KIND):
            if existing.config.get("template") == TEMPLATE_DAILY_REPORT:
                config = {**existing.config, "schedule": schedule}
                config["chat"] = TaskChat(channel=channel_uid, chat_id=owner.chat_id).model_dump()
                if agent:
                    config["agent"] = agent
                await self._resources.update_config(existing.uid, config, actor)
                if not existing.enabled:
                    await self._resources.set_enabled(existing.uid, True, actor)
                return await self._resources.get(existing.uid)
        config = {
            "schedule": schedule,
            "prompt": DAILY_REPORT_PROMPT,
            "chat": TaskChat(channel=channel_uid, chat_id=owner.chat_id).model_dump(),
            "session": "fresh",
            "material": MATERIAL_CHANNEL_DAY,
            "template": TEMPLATE_DAILY_REPORT,
        }
        if agent:
            config["agent"] = agent
        return await self.create("Daily report", config, actor=actor)

    # -- rules ------------------------------------------------------------------

    async def _check_follow_up(
        self, origin: TurnOrigin, chat: TaskChat, *, at: datetime, now: datetime
    ) -> None:
        ahead = at - now
        if ahead < FOLLOW_UP_MIN_AHEAD:
            raise ConfigValidationError("a follow-up is at least 5 minutes away")
        if ahead > FOLLOW_UP_MAX_AHEAD:
            raise ConfigValidationError("a follow-up is at most 7 days away")
        if origin.task_uid:
            if origin.chain_index >= CHAIN_MAX_RUNS:
                raise ConfigValidationError(
                    f"this chain already has {CHAIN_MAX_RUNS} follow-ups: give a conclusion now"
                )
            started = origin.chain_started_at or now
            if at > started + CHAIN_MAX_SPAN:
                raise ConfigValidationError(
                    "a follow-up chain lasts at most 7 days from its first follow-up"
                )
        waiting = [
            v
            for v in await self.waiting_in(chat.channel, chat.chat_id, chat.conversation_thread_id)
            if v.config.origin == "agent" and v.task.uid != origin.task_uid
        ]
        if len(waiting) >= FOLLOW_UPS_PER_THREAD:
            raise ConfigValidationError(
                f"{FOLLOW_UPS_PER_THREAD} follow-ups already wait in this thread; "
                "cancel one first (coffer__cancel_scheduled_task)"
            )

    async def _free_name(self, wanted: str) -> str:
        """``wanted``, or ``wanted (2)`` … when another task has that name."""
        base = wanted.strip()[: FREE_NAME_MAX_LEN - 6] or "Scheduled task"
        taken = [t.name for t in await self._resources.list(kind=KIND)]
        name, n = base, 1
        while any(same_free_name(name, other) for other in taken):
            n += 1
            name = f"{base} ({n})"
        return name
