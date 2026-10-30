"""One run of a scheduled task: from the history row to a turn in the chat
(spec channels "Run a scheduled task in the chat it names").

A run enters the chat the way a message does — through the turn driver, into
the chat's conversation or a fresh one, rendered by the same renderer and
queued behind whatever that conversation is doing (ADR
scheduled-tasks-are-turns-coffer-starts-in-a-chat). What a run adds is its
history row, opened ``running`` before anything else and closed with how the
turn ended, and the few ways a run fails before it is a turn at all: the
channel is not running, the chat is no longer paired, the conversation cannot
be opened. Those are told in the chat when the chat can still be reached.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from coffer.application.channel.conversation_ops import (
    ConversationPort,
    ensure_conversation,
    open_conversation,
)
from coffer.application.channel.ephemeral import safe_send
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.queued_inbound import QueuedInbound
from coffer.application.channel.schedule.message import run_message
from coffer.application.channel.schedule.ports import ScheduledRunRepoPort
from coffer.application.channel.scheduled_turn import ScheduledTurn
from coffer.application.channel.store_ports import (
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
)
from coffer.application.channel.turn_driver import TurnDriver
from coffer.application.channel.turn_finish import failure_line
from coffer.domain.channel.schedule import is_repeating
from coffer.domain.channel.scheduled_run import RunOutcome, ScheduledRun
from coffer.domain.channel.scheduled_task import (
    MATERIAL_CHANNEL_DAY,
    TEMPLATE_DAILY_REPORT,
    ScheduledTaskConfig,
)
from coffer.domain.errors import CofferError
from coffer.domain.resource import Resource

__all__ = ["RunRequest", "TaskRunner"]

_logger = logging.getLogger(__name__)

#: Gathers a task's material for a run (the day's channel conversations);
#: ``""`` when there is nothing to gather.
MaterialFor = Callable[[Resource, datetime], Awaitable[str]]
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
        binding: Callable[[str], ChannelBinding | None],
        peers: ChannelPeerRepoPort,
        threads: ChannelThreadConversationRepoPort,
        conversations: ConversationPort,
        driver: Callable[[], TurnDriver],
        material: MaterialFor | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._runs = runs
        self._binding = binding
        self._peers = peers
        self._threads = threads
        self._conversations = conversations
        self._driver = driver
        self._material = material
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
        config = ScheduledTaskConfig.model_validate(task.config)
        run = self._row(request, outcome="running")
        await self._runs.add(run)
        try:
            return await self._start(request, config, run)
        except Exception as exc:  # a run must end, whatever stopped it
            _logger.exception("channel.schedule.run_failed", extra={"task": task.uid})
            return await self._fail(task, run, f"Coffer could not start it ({type(exc).__name__})")

    async def _start(
        self, request: RunRequest, config: ScheduledTaskConfig, run: ScheduledRun
    ) -> ScheduledRun:
        task, chat = request.task, config.chat
        binding = self._binding(chat.channel)
        if binding is None:
            return await self._fail(task, run, "its channel is not running")
        peer = await self._peers.get_by_chat(chat.channel, chat.chat_id)
        if peer is None:
            return await self._fail(task, run, "its chat is no longer paired with the channel")

        async def tell(text: str) -> None:
            await safe_send(
                binding, chat.chat_id, text, thread_id=chat.thread_id, chat_kind=chat.chat_kind
            )

        material = ""
        if config.material == MATERIAL_CHANNEL_DAY and self._material is not None:
            material = await self._material(task, self._clock())
            if not material and config.template == TEMPLATE_DAILY_REPORT:
                return await self._end(task, run, "skipped", "no channel conversations today")
        try:
            if config.session == "fresh":
                conversation_id = await open_conversation(
                    self._conversations,
                    self._threads,
                    binding,
                    peer,
                    chat.conversation_thread_id,
                    chat_kind=chat.chat_kind,
                    prefer={
                        "preferred_agent": config.agent,
                        "preferred_model": config.model,
                        "preferred_cwd": config.cwd,
                    },
                )
            else:
                # A follow-up carries on: an idle conversation is not rolled over.
                conversation_id = await ensure_conversation(
                    self._conversations,
                    self._threads,
                    binding,
                    peer,
                    chat.conversation_thread_id,
                    chat_kind=chat.chat_kind,
                )
        except CofferError as e:
            await tell(failure_line(f"Scheduled task “{task.name}” could not start: {e}"))
            return await self._fail(task, run, str(e))
        await self._runs.note_conversation(run.run_id, conversation_id)
        run = replace(run, conversation_id=conversation_id)

        async def on_end(outcome: RunOutcome, reason: str) -> None:
            await self._end(task, run, outcome, reason)

        mention = config.mention
        item = QueuedInbound(
            text=run_message(
                name=task.name,
                uid=task.uid,
                config=config,
                created_at=task.created_at,
                due_at=request.due_at,
                now=self._clock(),
                late=request.late,
                manual=request.trigger == "manual",
                material=material,
            ),
            thread_id=chat.thread_id,
            chat_kind=chat.chat_kind,
            conversation_thread_id=chat.conversation_thread_id,
            mention_user_id=mention.user_id if mention else "",
            mention_user_email=mention.email if mention else "",
            mention_user_name=mention.name if mention else "",
            title_hint=task.name,
            scheduled=ScheduledTurn(
                task_uid=task.uid,
                run_id=run.run_id,
                repeats=is_repeating(config.schedule),
                on_end=on_end,
                chain_started_at=config.chain_started_at,
                chain_index=config.chain_index if config.origin == "agent" else 0,
            ),
        )
        try:
            await self._driver().submit_scheduled(binding, peer, item, conversation_id)
        except (CofferError, ValueError) as e:
            await tell(failure_line(f"Scheduled task “{task.name}” could not start: {e}"))
            return await self._fail(task, run, str(e))
        return run

    def _row(self, request: RunRequest, *, outcome: RunOutcome, reason: str = "") -> ScheduledRun:
        chat: Any = request.task.config.get("chat") or {}
        now = self._clock()
        return ScheduledRun(
            run_id=uuid.uuid4().hex,
            task_uid=request.task.uid,
            task_name=request.task.name,
            channel_uid=str(chat.get("channel", "")),
            chat_id=str(chat.get("chat_id", "")),
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
        await self._runs.finish(run.run_id, outcome=outcome, reason=reason, finished_at=finished)
        ended = replace(run, outcome=outcome, reason=reason, finished_at=finished)
        await self._settled(task, ended)
        return ended

    async def _settled(self, task: Resource, run: ScheduledRun) -> None:
        if self.on_settled is not None:
            try:
                await self.on_settled(task, run)
            except Exception:
                _logger.exception("channel.schedule.settle_failed", extra={"task": task.uid})
