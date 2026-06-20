"""TurnOrchestrator — runs one turn per conversation, agent-agnostically.

The orchestrator is pure chat-platform plumbing: it knows the agent-provider
registry and nothing about any specific agent. For each turn it asks the registry
for the conversation's provider, has the provider build a configured adapter, and
spawns the detached turn task (``turn_runner.run_turn_task``) which drives the
adapter and **publishes** events to the conversation's :class:`ConversationBus`.

Live mirror + pending queue (ADR-031)
-------------------------------------
Starting a turn is decoupled from consuming its events. Every turn's events are
published to a per-conversation bus; any number of clients ``subscribe`` (the web
``GET .../events`` stream). The web ``POST`` entry-point is ``enqueue_message``:
it starts the turn when idle or appends to a per-conversation **pending queue**
when a turn is running (the composer never locks). When a turn ends the queue
auto-advances FIFO, unless an interrupt paused it. The pending list is broadcast
as a ``QueueChanged`` event so every subscriber renders the same chips.

``start_turn`` is retained for the channel inbound seam: it starts a turn and
returns a dedicated event queue ending in a ``None`` sentinel (what the channel
renderer drains), while also publishing to the bus so the web observes a
channel-driven turn live.

Per-conversation state (in-flight turn, bus, pending queue) is process-global and
single-daemon by design; it lives in :mod:`turn_state`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

from coffer.application.audit_service import AuditService
from coffer.application.chat.bus import ConversationBus
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService, MessageRepo
from coffer.application.chat.turn_runner import run_turn_task
from coffer.application.chat.turn_state import (
    _ACTIVE_TURNS,
    _BUSES,
    _PENDING,
    _ActiveTurn,
    _PendingState,
)
from coffer.application.chat.turn_state import active_turns as active_turns
from coffer.application.chat.turn_state import clear_active_turns as clear_active_turns
from coffer.domain.chat.events import AgentEvent, QueueChanged, TurnError
from coffer.domain.chat.message import Role, TextBlock
from coffer.domain.errors import TurnInProgress

log = logging.getLogger(__name__)


class TurnOrchestrator:
    """Drive one agent turn per conversation, agent-agnostically."""

    def __init__(
        self,
        *,
        chat_service: ChatService,
        registry: AgentProviderRegistry,
        audit: AuditService,
    ) -> None:
        self._chat = chat_service
        self._registry = registry
        self._audit = audit
        # Keep references to fire-and-forget advance tasks so they are not GC'd
        # mid-flight; each discards itself on completion.
        self._bg_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # Subscriptions (web GET .../events)
    # ------------------------------------------------------------------

    def subscribe(self, conversation_id: str) -> asyncio.Queue[AgentEvent | None]:
        """Attach a live-events subscriber, replaying the in-flight turn + the
        current pending-queue snapshot so it catches up immediately."""
        return self._bus_for(conversation_id).subscribe()

    def unsubscribe(self, conversation_id: str, queue: asyncio.Queue[AgentEvent | None]) -> None:
        bus = _BUSES.get(conversation_id)
        if bus is not None:
            bus.unsubscribe(queue)

    def pending(self, conversation_id: str) -> list[str]:
        """The conversation's current ordered pending-message texts."""
        state = _PENDING.get(conversation_id)
        return list(state.queue) if state is not None else []

    # ------------------------------------------------------------------
    # Web entry points (POST .../messages, PUT .../pending)
    # ------------------------------------------------------------------

    async def enqueue_message(self, conversation_id: str, user_text: str) -> bool:
        """Start a turn for the message, or enqueue it behind the in-flight one.

        Returns ``True`` when the message was queued, ``False`` when its turn
        started immediately. Raises ``ConversationNotFound`` when the conversation
        does not exist. The composer never locks — a message sent during a turn is
        never rejected (revises FR-018, ADR-031).
        """
        await self._chat.get_conversation(conversation_id)  # raises ConversationNotFound -> 404
        state = self._pending_for(conversation_id)
        start_now = conversation_id not in _ACTIVE_TURNS and not state.paused and not state.queue
        state.paused = False
        if start_now:
            await self._begin_turn(conversation_id, user_text, primary_queue=None)
            self._broadcast_queue_changed(conversation_id)
            return False
        state.queue.append(user_text)
        self._broadcast_queue_changed(conversation_id)
        # Unpaused above — drain the head if the conversation is now idle (e.g. a
        # plain send after an interrupt resumes the held queue).
        await self._maybe_advance(conversation_id)
        return True

    async def set_pending(self, conversation_id: str, texts: Sequence[str]) -> list[str]:
        """Replace the pending queue (resume / drop / reorder). Unpauses and
        starts the next turn when none is in flight. Returns the resulting queue.
        """
        await self._chat.get_conversation(conversation_id)  # raises ConversationNotFound -> 404
        state = self._pending_for(conversation_id)
        state.queue = list(texts)
        state.paused = False
        self._broadcast_queue_changed(conversation_id)
        await self._maybe_advance(conversation_id)
        return self.pending(conversation_id)

    # ------------------------------------------------------------------
    # Channel entry point (kept seam): start + return a drainable queue
    # ------------------------------------------------------------------

    async def start_turn(
        self, conversation_id: str, user_text: str
    ) -> asyncio.Queue[AgentEvent | None]:
        """Start a turn and return a dedicated event queue ending in ``None``.

        Used by the channel inbound renderer. Raises ``TurnInProgress`` if a turn
        is already active. The turn also publishes to the conversation bus, so the
        web observes a channel-driven turn live.
        """
        if conversation_id in _ACTIVE_TURNS:
            raise TurnInProgress(conversation_id)
        primary: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        await self._begin_turn(conversation_id, user_text, primary_queue=primary)
        return primary

    # ------------------------------------------------------------------
    # Turn control
    # ------------------------------------------------------------------

    def interrupt_turn(self, conversation_id: str) -> None:
        """Stop a running turn (keeping its partial output) and pause the queue.

        A no-op when no turn is in flight. Pausing holds queued messages until the
        owner resumes (any send / ``set_pending`` clears the pause).
        """
        active = _ACTIVE_TURNS.get(conversation_id)
        if active is not None and active.task is not None and not active.task.done():
            active.interrupted = True
            state = _PENDING.get(conversation_id)
            if state is not None:
                state.paused = True
            active.task.cancel()
            log.debug("Interrupted turn for conversation %s", conversation_id)

    def cancel_turn(self, conversation_id: str) -> None:
        """Cancel and discard a running turn, drop the pending queue, and close the
        bus (used when the conversation is deleted).

        Does NOT pop ``_ACTIVE_TURNS``; the task's ``finally`` performs an
        ownership-checked removal so a racing start cannot have its fresh entry
        evicted.
        """
        active = _ACTIVE_TURNS.get(conversation_id)
        if active is not None and active.task is not None and not active.task.done():
            active.task.cancel()
            log.debug("Cancelled turn for conversation %s", conversation_id)
        _PENDING.pop(conversation_id, None)
        bus = _BUSES.pop(conversation_id, None)
        if bus is not None:
            bus.close()

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

    def _bus_for(self, conversation_id: str) -> ConversationBus:
        bus = _BUSES.get(conversation_id)
        if bus is None:
            bus = ConversationBus()
            _BUSES[conversation_id] = bus
        return bus

    def _pending_for(self, conversation_id: str) -> _PendingState:
        state = _PENDING.get(conversation_id)
        if state is None:
            state = _PendingState()
            _PENDING[conversation_id] = state
        return state

    def _broadcast_queue_changed(self, conversation_id: str) -> None:
        self._bus_for(conversation_id).publish_queue_changed(
            QueueChanged(pending=self.pending(conversation_id))
        )

    async def _maybe_advance(self, conversation_id: str) -> None:
        """Start the next pending message if the conversation is idle + unpaused."""
        state = _PENDING.get(conversation_id)
        if state is None or conversation_id in _ACTIVE_TURNS or state.paused or not state.queue:
            return
        text = state.queue.pop(0)
        self._broadcast_queue_changed(conversation_id)
        try:
            await self._begin_turn(conversation_id, text, primary_queue=None)
        except Exception:
            log.exception("auto-advance turn failed for conversation %s", conversation_id)
            # Re-insert the head and pause so the message is neither lost nor
            # retried in a spin; the owner resumes (send / set_pending) after
            # fixing the cause (FR-018a — a queued message must not vanish).
            state.queue.insert(0, text)
            state.paused = True
            self._broadcast_queue_changed(conversation_id)
            self._bus_for(conversation_id).publish(
                TurnError(code="INTERNAL_ERROR", message="failed to start queued turn")
            )

    async def _begin_turn(
        self,
        conversation_id: str,
        user_text: str,
        *,
        primary_queue: asyncio.Queue[AgentEvent | None] | None,
    ) -> None:
        """Reserve the slot, build the adapter, persist the user message, spawn the
        turn task. Callers guarantee no turn is currently active."""
        bus = self._bus_for(conversation_id)
        active = _ActiveTurn(bus=bus, primary_queue=primary_queue)
        # Reserve synchronously — no ``await`` before this insert.
        _ACTIVE_TURNS[conversation_id] = active
        bus.begin_turn()
        try:
            conv = await self._chat.get_conversation(conversation_id)
            provider = self._registry.get(conv.agent_key)
            adapter = await provider.build_adapter(conversation_id)
            await self._chat.append_message(
                conversation_id,
                role=Role.USER,
                content=[TextBlock(text=user_text)],
                status="complete",
            )
        except BaseException:
            # Anything failed before the task spawned — release the reservation.
            if _ACTIVE_TURNS.get(conversation_id) is active:
                del _ACTIVE_TURNS[conversation_id]
            if primary_queue is not None:
                primary_queue.put_nowait(None)
            raise

        task = asyncio.create_task(
            run_turn_task(
                conversation_id=conversation_id,
                active=active,
                adapter=adapter,
                chat=self._chat,
                audit=self._audit,
            ),
            name=f"turn:{conversation_id}",
        )
        active.task = task
        task.add_done_callback(self._advance_callback(conversation_id))

    def _advance_callback(self, conversation_id: str) -> Callable[[asyncio.Task[None]], None]:
        def _cb(_task: asyncio.Task[None]) -> None:
            advance = asyncio.create_task(self._maybe_advance(conversation_id))
            self._bg_tasks.add(advance)
            advance.add_done_callback(self._bg_tasks.discard)

        return _cb
