"""TurnOrchestrator — runs one turn per conversation, agent-agnostically.

The orchestrator is pure chat-platform plumbing: it knows the agent-provider
registry and nothing about any specific agent. For each turn it asks the
registry for the conversation's provider, has the provider build a configured
adapter, drives ``adapter.run_turn(history)``, **publishes** the events to the
conversation's :class:`ConversationBus`, and persists the assistant message.

Live mirror + pending queue (ADR-031)
-------------------------------------
Starting a turn is decoupled from consuming its events. Every turn's events are
published to a per-conversation :class:`ConversationBus`; any number of clients
``subscribe`` to it (the web ``GET .../events`` stream). The web ``POST``
entry-point is ``enqueue_message``: it starts the turn when idle or appends to a
per-conversation **pending queue** when a turn is running (the composer never
locks). When a turn ends the queue auto-advances FIFO, unless it was paused by an
interrupt. The pending list is broadcast as a ``QueueChanged`` event so every
subscriber renders the same chips.

``start_turn`` is retained for the channel inbound seam: it starts a turn and
returns a dedicated event queue ending in a ``None`` sentinel (what the channel
renderer drains), while *also* publishing to the bus so the web observes a
channel-driven turn live.

Architecture notes
------------------
- ``_ACTIVE_TURNS`` / ``_BUSES`` / ``_PENDING`` are module-level (process-global,
  single-daemon by design — ADR-031). The active-turn entry is registered
  synchronously, right after the ``TurnInProgress`` guard / idle check, so two
  concurrent starts cannot both pass.
- Interruption vs. deletion: both cancel the task; ``_ActiveTurn.interrupted``
  tells the ``CancelledError`` handler whether to persist the partial message
  (interrupt) or discard it (delete). Interrupt also pauses the pending queue.
- A client disconnect cancels only its subscriber drain, not the turn task, so
  the assistant message is still persisted (research.md §7).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from coffer.application.audit_service import AuditService
from coffer.application.chat.bus import ConversationBus
from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService, MessageRepo
from coffer.application.chat.turn_persistence import (
    finalize_assistant_message,
    recover_placeholder_id,
)
from coffer.domain.chat.events import (
    AgentEvent,
    QueueChanged,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)
from coffer.domain.chat.message import (
    Message,
    Role,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from coffer.domain.errors import TurnInProgress

log = logging.getLogger(__name__)


@dataclass
class _ActiveTurn:
    """In-process record of one conversation's in-flight turn."""

    bus: ConversationBus
    # A dedicated event queue for a ``start_turn`` caller (the channel renderer);
    # ``None`` for a web turn, which observes via the bus instead. When present it
    # receives every event plus a ``None`` end-of-stream sentinel.
    primary_queue: asyncio.Queue[AgentEvent | None] | None = None
    task: asyncio.Task[None] | None = None
    interrupted: bool = field(default=False)


@dataclass
class _PendingState:
    """A conversation's pending-message queue (ADR-031)."""

    queue: list[str] = field(default_factory=list)
    # Set by an interrupt; blocks auto-advance until the owner resumes (any
    # ``enqueue_message`` / ``set_pending`` clears it).
    paused: bool = False


# Module-level, process-global (single daemon). conversation_id → state.
_ACTIVE_TURNS: dict[str, _ActiveTurn] = {}
_BUSES: dict[str, ConversationBus] = {}
_PENDING: dict[str, _PendingState] = {}


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

        Returns ``True`` when the message was queued (a turn was already running),
        ``False`` when its turn started immediately. Raises ``ConversationNotFound``
        when the conversation does not exist. The composer never locks — a message
        sent during a turn is never rejected (revises FR-018, ADR-031).
        """
        await self._chat.get_conversation(conversation_id)  # raises ConversationNotFound -> 404
        state = self._pending_for(conversation_id)
        start_now = conversation_id not in _ACTIVE_TURNS and not state.paused and not state.queue
        state.paused = False
        if start_now:
            # Start directly — the message is the head and runs at once.
            await self._begin_turn(conversation_id, user_text, primary_queue=None)
        else:
            state.queue.append(user_text)
        self._broadcast_queue_changed(conversation_id)
        return not start_now

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
            self._run_turn(conversation_id, active, adapter),
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

    async def _run_turn(
        self,
        conversation_id: str,
        active: _ActiveTurn,
        adapter: AgentAdapter,
    ) -> None:
        """Async task body: drive the adapter, publish events, persist the result."""
        bus = active.bus

        def emit(event: AgentEvent) -> None:
            bus.publish(event)
            if active.primary_queue is not None:
                active.primary_queue.put_nowait(event)

        text_parts: list[str] = []
        tool_use_blocks: list[ToolUseBlock] = []
        tool_result_blocks: list[ToolResultBlock] = []
        final_done: TurnDone | None = None
        error_event: TurnError | None = None
        # An adapter may expose the resolved model id so the assistant message can
        # record it. Other adapters need not; best-effort read.
        model_id: str | None = getattr(adapter, "model_id", None)
        placeholder_id: str | None = None
        append_task: asyncio.Task[Message] | None = None

        try:
            history = await self._chat.list_messages(conversation_id)
            # Write a ``streaming`` placeholder assistant row BEFORE the first
            # event. A daemon crash mid-turn then leaves a row the startup sweep
            # flips to ``failed`` (FR-022). It is finalised in place on completion
            # (one row, no dup). The write runs as a shielded task: a cancellation
            # landing between the row's commit and the id assignment leaves the
            # task running, and the CancelledError handler recovers the id.
            append_task = asyncio.create_task(
                self._chat.append_message(
                    conversation_id,
                    role=Role.ASSISTANT,
                    content=[],
                    status="streaming",
                    model_id=model_id,
                )
            )
            placeholder_id = (await asyncio.shield(append_task)).id

            async for event in await adapter.run_turn(history=history):
                emit(event)
                if isinstance(event, TextDelta):
                    text_parts.append(event.text)
                elif isinstance(event, ToolCall):
                    tool_use_blocks.append(
                        ToolUseBlock(
                            tool_use_id=event.tool_use_id,
                            tool_name=event.tool_name,
                            tool_input=event.tool_input,
                        )
                    )
                elif isinstance(event, ToolResult):
                    tool_result_blocks.append(
                        ToolResultBlock(
                            tool_use_id=event.tool_use_id,
                            tool_name=event.tool_name,
                            output=event.output,
                            error=event.error,
                        )
                    )
                elif isinstance(event, TurnDone):
                    final_done = event
                elif isinstance(event, TurnError):
                    error_event = event
                    log.warning(
                        "Turn for conversation %s ended with %s: %s",
                        conversation_id,
                        event.code,
                        event.message,
                    )
                # TurnStarted / QueueChanged: forwarded only, not message content.

            await self._finalize_assistant_message(
                conversation_id=conversation_id,
                message_id=placeholder_id,
                model_id=model_id,
                text_parts=text_parts,
                tool_use_blocks=tool_use_blocks,
                tool_result_blocks=tool_result_blocks,
                final_done=final_done,
                error_event=error_event,
            )
        except asyncio.CancelledError:
            # The cancel may have landed while the placeholder write was still in
            # flight; recover the committed row's id so it is not orphaned.
            placeholder_id = await recover_placeholder_id(placeholder_id, append_task)
            if active.interrupted:
                # User interrupt: keep whatever the agent produced. Emit a terminal
                # event and finalise the partial message. The finalise is shielded
                # so a second cancellation (e.g. the conversation is deleted while
                # this interrupt is mid-write) cannot abort the write half-done.
                done = TurnDone(
                    prompt_tokens=None, completion_tokens=None, stop_reason="interrupted"
                )
                emit(done)
                await asyncio.shield(
                    self._finalize_assistant_message(
                        conversation_id=conversation_id,
                        message_id=placeholder_id,
                        model_id=model_id,
                        text_parts=text_parts,
                        tool_use_blocks=tool_use_blocks,
                        tool_result_blocks=tool_result_blocks,
                        final_done=done,
                        error_event=None,
                    )
                )
                # Cancellation handled — do NOT re-raise.
            else:
                # Conversation deleted: discard the partial turn entirely — remove
                # the placeholder so no orphan streaming row remains.
                if placeholder_id is not None:
                    await asyncio.shield(self._chat.delete_message(placeholder_id))
                log.debug("Turn for conversation %s cancelled and discarded", conversation_id)
                raise
        except Exception as exc:
            log.exception("Unexpected error in turn task for conversation %s", conversation_id)
            error_event = TurnError(code="INTERNAL_ERROR", message=str(exc))
            emit(error_event)
            # placeholder_id may be None when the placeholder write itself failed;
            # _finalize falls back to appending a failed row so the turn still
            # leaves a persisted + audited trace.
            await self._finalize_assistant_message(
                conversation_id=conversation_id,
                message_id=placeholder_id,
                model_id=model_id,
                text_parts=text_parts,
                tool_use_blocks=tool_use_blocks,
                tool_result_blocks=tool_result_blocks,
                final_done=final_done,
                error_event=error_event,
            )
        finally:
            # Ownership-checked removal — only evict our own entry so a racing
            # start that registered a fresh entry is not lost.
            if _ACTIVE_TURNS.get(conversation_id) is active:
                del _ACTIVE_TURNS[conversation_id]
            bus.end_turn()
            # Close the channel's dedicated queue so its renderer never hangs.
            if active.primary_queue is not None:
                active.primary_queue.put_nowait(None)

    async def _finalize_assistant_message(self, **kwargs: Any) -> None:
        """Finalize + audit the turn's assistant message (see turn_persistence)."""
        await finalize_assistant_message(chat=self._chat, audit=self._audit, **kwargs)


# ---------------------------------------------------------------------------
# Test / monitoring helpers
# ---------------------------------------------------------------------------


def active_turns() -> dict[str, _ActiveTurn]:
    """Expose the active-turns registry (for testing/monitoring only)."""
    return _ACTIVE_TURNS


def clear_active_turns() -> None:
    """Clear all per-conversation orchestrator state (test teardown only)."""
    _ACTIVE_TURNS.clear()
    _BUSES.clear()
    _PENDING.clear()
