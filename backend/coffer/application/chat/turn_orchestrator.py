"""TurnOrchestrator — runs one turn per conversation, agent-agnostically.

The orchestrator is pure chat-platform plumbing: it knows the agent-provider
registry and nothing about any specific agent. For each turn it asks the registry
for the conversation's provider, has the provider build a configured adapter, and
spawns the detached turn task (``turn_runner.run_turn_task``) which drives the
adapter and **publishes** events to the conversation's :class:`ConversationBus`.

Turn lifecycle + pending queue (spec channels FR-050…FR-054)
-------------------------------------
Starting a turn is decoupled from consuming its events. Every turn's events are
published to a per-conversation bus; any number of clients ``subscribe`` (the web
``GET .../events`` stream). The one entry point for a message — from the web
``POST`` and from a channel alike — is ``enqueue_message``: it starts the turn
when idle or appends to the conversation's **pending queue** when a turn is
running (the composer never locks, the bot never says "busy" for the tenth
message). When a turn ends the queue auto-advances FIFO, unless an interrupt
paused it. The pending list is broadcast as a ``QueueChanged`` event so every
subscriber — the web tabs and the channel alike — renders the same chips.

A channel message rides the same queue with two extras: the attachments and
title hint it persists into the user message, and an ``on_start`` sink that is
handed a dedicated event queue (ending in ``None``) the moment its turn begins,
which is what the channel renderer drains. The web observes the same turn on
the bus.

``start_turn`` is the immediate-or-refuse seam (start now or raise
``TurnInProgress``); it is what tests that need a turn *right now* use.

Per-conversation state (bus, in-flight turn, pending queue) is process-global
and single-daemon by design; it lives in :mod:`turn_state` and is released
once a conversation is idle with nobody watching.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService, MessageRepo
from coffer.application.chat.turn_runner import (
    DEFAULT_TURN_IDLE_TIMEOUT_SECONDS,
    run_turn_task,
)
from coffer.application.chat.turn_state import _STATES as _STATES
from coffer.application.chat.turn_state import (
    ActiveTurn,
    PendingMessage,
    TurnSink,
    TurnState,
    evict_if_idle,
    peek,
    state_for,
)
from coffer.application.chat.turn_state import active_turns as active_turns
from coffer.application.chat.turn_state import clear_active_turns as clear_active_turns
from coffer.application.chat.turn_state import held_conversations as held_conversations
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.errors import TurnInProgress
from coffer.domain.chat.events import AgentEvent, QueueChanged, TurnError
from coffer.domain.chat.message import AttachmentBlock, Role, TextBlock

log = logging.getLogger(__name__)


class TurnOrchestrator:
    """Drive one agent turn per conversation, agent-agnostically."""

    def __init__(
        self,
        *,
        chat_service: ChatService,
        registry: AgentProviderRegistry,
        idle_timeout: float | None = DEFAULT_TURN_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self._chat = chat_service
        self._registry = registry
        # How long a turn may go without producing an event before the watchdog
        # cancels it (``turn_runner``); ``None`` disables the watchdog.
        self._idle_timeout = idle_timeout
        # Keep references to fire-and-forget advance tasks so they are not GC'd
        # mid-flight; each discards itself on completion.
        self._bg_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # Subscriptions (web GET .../events)
    # ------------------------------------------------------------------

    def subscribe(self, conversation_id: str) -> asyncio.Queue[AgentEvent | None]:
        """Attach a live-events subscriber, replaying the in-flight turn + the
        current pending-queue snapshot so it catches up immediately."""
        return state_for(conversation_id).bus.subscribe()

    def unsubscribe(self, conversation_id: str, queue: asyncio.Queue[AgentEvent | None]) -> None:
        state = peek(conversation_id)
        if state is not None:
            state.bus.unsubscribe(queue)
            evict_if_idle(conversation_id)

    def pending(self, conversation_id: str) -> list[str]:
        """The conversation's current ordered pending-message texts."""
        state = peek(conversation_id)
        return [m.text for m in state.queue] if state is not None else []

    # ------------------------------------------------------------------
    # The entry point for a message — web POST .../messages and channels alike
    # ------------------------------------------------------------------

    async def enqueue_message(
        self,
        conversation_id: str,
        user_text: str,
        *,
        attachments: Sequence[Attachment] = (),
        title_hint: str | None = None,
        on_start: TurnSink | None = None,
    ) -> bool:
        """Start a turn for the message, or enqueue it behind the in-flight one.

        Returns ``True`` when the message was queued, ``False`` when its turn
        started immediately. Raises ``ConversationNotFound`` when the conversation
        does not exist. A message sent during a turn is never rejected (spec
        channels FR-050) — from the web composer or from a channel.

        ``attachments`` (channel media) are persisted into the user message as
        references (FR-033) and ``title_hint`` names a conversation still under
        its placeholder title (FR-048). ``on_start`` is a channel's renderer
        hook: called with the turn's dedicated event queue (ending in ``None``)
        the moment the turn begins — now, or when the queue reaches it.
        """
        await self._chat.get_conversation(conversation_id)  # raises ConversationNotFound -> 404
        state = state_for(conversation_id)
        message = PendingMessage(
            text=user_text,
            attachments=tuple(attachments),
            title_hint=title_hint,
            on_start=on_start,
        )
        start_now = state.active is None and not state.paused and not state.queue
        state.paused = False
        if start_now:
            await self._begin_turn(conversation_id, message)
            self._broadcast_queue_changed(conversation_id)
            return False
        state.queue.append(message)
        self._broadcast_queue_changed(conversation_id)
        # Unpaused above — drain the head if the conversation is now idle (e.g. a
        # plain send after an interrupt resumes the held queue).
        await self._maybe_advance(conversation_id)
        return True

    async def set_pending(self, conversation_id: str, texts: Sequence[str]) -> list[str]:
        """Replace the pending queue (resume / drop / reorder). Unpauses and
        starts the next turn when none is in flight. Returns the resulting queue.

        A queued message whose text is unchanged keeps what it carried
        (attachments, its channel renderer): reordering the queue from the web
        must not turn a channel message into a web one.
        """
        await self._chat.get_conversation(conversation_id)  # raises ConversationNotFound -> 404
        state = state_for(conversation_id)
        state.queue = _reconcile(state.queue, texts)
        state.paused = False
        self._broadcast_queue_changed(conversation_id)
        await self._maybe_advance(conversation_id)
        return self.pending(conversation_id)

    # ------------------------------------------------------------------
    # Immediate-or-refuse seam
    # ------------------------------------------------------------------

    async def start_turn(
        self,
        conversation_id: str,
        user_text: str,
        *,
        attachments: Sequence[Attachment] = (),
        title_hint: str | None = None,
    ) -> asyncio.Queue[AgentEvent | None]:
        """Start a turn NOW and return a dedicated event queue ending in ``None``.

        Raises ``TurnInProgress`` if a turn is already active — the caller wanted
        this turn and no other, not a place in the queue. The turn also publishes
        to the conversation bus, so a web observer sees it live.
        """
        state = state_for(conversation_id)
        if state.active is not None:
            raise TurnInProgress(conversation_id)
        primary: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        message = PendingMessage(
            text=user_text, attachments=tuple(attachments), title_hint=title_hint
        )
        await self._begin_turn(conversation_id, message, primary_queue=primary)
        return primary

    # ------------------------------------------------------------------
    # Turn control
    # ------------------------------------------------------------------

    def interrupt_turn(self, conversation_id: str) -> None:
        """Stop a running turn (keeping its partial output) and pause the queue.

        A no-op when no turn is in flight. Pausing holds queued messages until the
        owner resumes (any send / ``set_pending`` clears the pause) — FR-051.
        """
        state = peek(conversation_id)
        if state is None:
            return
        active = state.active
        if active is not None and active.task is not None and not active.task.done():
            active.interrupted = True
            state.paused = True
            active.task.cancel()
            log.debug("Interrupted turn for conversation %s", conversation_id)

    def cancel_turn(self, conversation_id: str) -> None:
        """Cancel and discard a running turn, drop the pending queue, and close the
        bus (used when the conversation is deleted).

        The whole state is dropped here; the task's ``finally`` release is
        ownership-checked, so a racing start's fresh state is never evicted.
        """
        state = _STATES.pop(conversation_id, None)
        if state is None:
            return
        active = state.active
        if active is not None and active.task is not None and not active.task.done():
            active.task.cancel()
            log.debug("Cancelled turn for conversation %s", conversation_id)
        state.queue.clear()
        state.bus.close()

    @staticmethod
    async def sweep_streaming_messages(message_repo: MessageRepo) -> int:
        """Flip any lingering ``status='streaming'`` rows to ``'failed'``.

        Called once at daemon startup to recover from a prior crash. Returns the
        number of rows flipped.
        """
        return await message_repo.sweep_streaming()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _broadcast_queue_changed(self, conversation_id: str) -> None:
        state_for(conversation_id).bus.publish_queue_changed(
            QueueChanged(pending=self.pending(conversation_id))
        )

    async def _maybe_advance(self, conversation_id: str) -> None:
        """Start the next pending message if the conversation is idle + unpaused;
        release the conversation's state when there is nothing left to hold."""
        state = peek(conversation_id)
        if state is None:
            return
        if state.active is not None or state.paused or not state.queue:
            evict_if_idle(conversation_id)
            return
        message = state.queue.pop(0)
        self._broadcast_queue_changed(conversation_id)
        try:
            await self._begin_turn(conversation_id, message)
        except Exception:
            log.exception("auto-advance turn failed for conversation %s", conversation_id)
            # Re-insert the head and pause so the message is neither lost nor
            # retried in a spin; the owner resumes (send / set_pending) after
            # fixing the cause (FR-018a — a queued message must not vanish).
            state.queue.insert(0, message)
            state.paused = True
            self._broadcast_queue_changed(conversation_id)
            error = TurnError(code="INTERNAL_ERROR", message="failed to start queued turn")
            state.bus.publish(error)
            if message.on_start is not None:
                # A channel has no queue chips to look at: hand its renderer a
                # stream that carries the failure and ends, so the chat hears it.
                failed: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
                failed.put_nowait(error)
                failed.put_nowait(None)
                message.on_start(failed)

    async def _begin_turn(
        self,
        conversation_id: str,
        message: PendingMessage,
        *,
        primary_queue: asyncio.Queue[AgentEvent | None] | None = None,
    ) -> None:
        """Reserve the slot, build the adapter, persist the user message, spawn the
        turn task. Callers guarantee no turn is currently active.

        Attachments (channel media) are persisted INTO the user message as
        ``AttachmentBlock`` references (path/mime/filename, no bytes) after the
        text — the single source of truth. The turn task re-materialises them for
        the adapter by reading them back from history (FR-033), so they survive a
        daemon restart and are not threaded down as a separate param. The title
        hint rides along to the persisted user message, where the
        placeholder-title rule uses it instead of the raw text (FR-048)."""
        state = state_for(conversation_id)
        if message.on_start is not None and primary_queue is None:
            primary_queue = asyncio.Queue()
        active = ActiveTurn(bus=state.bus, primary_queue=primary_queue)
        # Reserve synchronously — no ``await`` before this assignment.
        state.active = active
        state.bus.begin_turn()
        try:
            conv = await self._chat.get_conversation(conversation_id)
            provider = self._registry.get(conv.agent_key)
            adapter = await provider.build_adapter(conversation_id)
            await self._chat.append_message(
                conversation_id,
                role=Role.USER,
                content=[
                    TextBlock(text=message.text),
                    *(
                        AttachmentBlock(path=a.path, mime=a.mime, filename=a.filename)
                        for a in message.attachments
                    ),
                ],
                status="complete",
                title_hint=message.title_hint,
            )
        except BaseException:
            # Anything failed before the task spawned — release the reservation.
            if state.active is active:
                state.active = None
            if primary_queue is not None:
                primary_queue.put_nowait(None)
            raise

        task = asyncio.create_task(
            run_turn_task(
                conversation_id=conversation_id,
                active=active,
                adapter=adapter,
                chat=self._chat,
                idle_timeout=self._idle_timeout,
            ),
            name=f"turn:{conversation_id}",
        )
        active.task = task
        task.add_done_callback(self._advance_callback(conversation_id))
        if message.on_start is not None and primary_queue is not None:
            # After the task exists, so a renderer that stops the turn finds it.
            message.on_start(primary_queue)

    def _advance_callback(self, conversation_id: str) -> Callable[[asyncio.Task[None]], None]:
        def _cb(_task: asyncio.Task[None]) -> None:
            advance = asyncio.create_task(self._maybe_advance(conversation_id))
            self._bg_tasks.add(advance)
            advance.add_done_callback(self._bg_tasks.discard)

        return _cb


def _reconcile(queue: list[PendingMessage], texts: Sequence[str]) -> list[PendingMessage]:
    """The queue ``texts`` describes, reusing an existing entry for each text it
    still contains (first unused match wins) so a reordered or partly-dropped
    queue keeps every message's attachments and renderer."""
    unused = list(queue)
    result: list[PendingMessage] = []
    for text in texts:
        match = next((m for m in unused if m.text == text), None)
        if match is not None:
            unused.remove(match)
            result.append(match)
        else:
            result.append(PendingMessage(text=text))
    return result


__all__ = [
    "TurnOrchestrator",
    "TurnState",
    "active_turns",
    "clear_active_turns",
    "held_conversations",
]
