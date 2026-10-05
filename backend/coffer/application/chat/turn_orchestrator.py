"""TurnOrchestrator — runs one turn per conversation, agent-agnostically.

The orchestrator is pure chat-platform plumbing: it knows the agent-provider
registry and nothing about any specific agent. For each turn it asks the registry
for the conversation's provider, has the provider build a configured adapter, and
spawns the detached turn task (``turn_runner.run_turn_task``) which drives the
adapter and **publishes** events to the conversation's :class:`ConversationBus`.

Turn lifecycle + pending queue (spec chat)
------------------------------------------
The one entry point for a message — from a channel — is ``enqueue_message``: it
starts the turn when idle or appends to the conversation's **pending queue** when
a turn is running. The orchestrator itself never refuses a message; the channel
turn driver bounds its own queue (``channel.turn_driver.QUEUE_MAX``) and tells
the sender when a message overflows it (spec channels). When a turn ends the
queue auto-advances FIFO, unless an interrupt paused it.

A channel message rides the queue with two extras: the attachments and title
hint it carries into its turn, and an ``on_start`` sink that is handed a
dedicated event queue (ending in ``None``) the moment its turn begins, which is
what the channel renderer drains. The turn's prompt and attachments go to the
adapter directly; Coffer stores no message — the agent's own session holds the
conversation. Per-conversation state (in-flight turn, pending queue) is
process-global and lives in :mod:`turn_state`, released once a conversation is
idle with nobody watching.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence

from coffer.application.chat import questions
from coffer.application.chat.ports import SessionInUsePort
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_runner import (
    DEFAULT_TURN_IDLE_TIMEOUT_SECONDS,
    run_turn_task,
)
from coffer.application.chat.turn_state import _STATES as _STATES
from coffer.application.chat.turn_state import (
    ActiveTurn,
    PendingMessage,
    TurnSink,
    TurnsStopping,
    TurnState,
    evict_if_idle,
    is_stopping,
    peek,
    state_for,
)
from coffer.application.chat.turn_state import active_turns as active_turns
from coffer.application.chat.turn_state import clear_active_turns as clear_active_turns
from coffer.application.chat.turn_state import held_conversations as held_conversations
from coffer.application.runtime import correlation
from coffer.application.runtime.supervisor import spawn
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.errors import SessionInUse
from coffer.domain.chat.events import (
    SESSION_IN_USE,
    SESSION_IN_USE_MESSAGE,
    AgentEvent,
    TurnError,
)

log = logging.getLogger(__name__)


class TurnOrchestrator:
    """Drive one agent turn per conversation, agent-agnostically."""

    def __init__(
        self,
        *,
        chat_service: ChatService,
        registry: AgentProviderRegistry,
        idle_timeout: float | None = DEFAULT_TURN_IDLE_TIMEOUT_SECONDS,
        session_in_use: SessionInUsePort | None = None,
    ) -> None:
        self._chat = chat_service
        self._registry = registry
        # Asked before a turn resumes a native session (spec chat "Run a session
        # in one place at a time"); ``None`` never refuses.
        self._session_in_use = session_in_use
        # How long a turn may go without producing an event before the watchdog
        # cancels it (``turn_runner``); ``None`` disables the watchdog.
        self._idle_timeout = idle_timeout
        # Keep references to fire-and-forget advance tasks so they are not GC'd
        # mid-flight; each discards itself on completion.
        self._bg_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # The pending queue
    # ------------------------------------------------------------------

    def pending(self, conversation_id: str) -> list[str]:
        """The conversation's current ordered pending-message texts."""
        state = peek(conversation_id)
        return [m.text for m in state.queue] if state is not None else []

    # ------------------------------------------------------------------
    # The entry point for a message
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

        Returns ``True`` when the message was queued, ``False`` when its turn started
        immediately. Raises ``ConversationNotFound`` when the conversation does not
        exist. A message sent during a turn is never rejected (spec chat "Queue messages
        sent during a turn").

        ``attachments`` (channel media) go to the adapter with the turn and
        ``title_hint`` names a conversation still under its placeholder title.
        ``on_start`` is a channel's renderer hook: called with the turn's dedicated
        event queue (ending in ``None``) the moment the turn begins — now, or when
        the queue reaches it.
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
        if start_now and not is_stopping():
            try:
                started = await self._begin_turn(conversation_id, message)
            except TurnsStopping:
                pass  # the daemon began stopping mid-start: hold it in the queue
            except BaseException:
                # The start was refused (a missing agent, a rejected config): the
                # state built for it must not linger for the process's life.
                evict_if_idle(conversation_id)
                raise
            else:
                if not started:
                    evict_if_idle(conversation_id)
                return False
        # Held while the daemon stops — the in-memory queue goes with it.
        state.queue.append(message)
        # Unpaused above — drain the head if the conversation is now idle (e.g. a
        # plain send after an interrupt resumes the held queue).
        await self._maybe_advance(conversation_id)
        return True

    # ------------------------------------------------------------------
    # Turn control
    # ------------------------------------------------------------------

    def interrupt_turn(self, conversation_id: str) -> bool:
        """Stop a running turn (keeping its partial output) and pause the queue;
        ``True`` when there was one to stop.

        A no-op when no turn is in flight. Pausing holds queued messages until the owner
        resumes (any send clears the pause) — spec chat "Pause the
        pending queue on interrupt".
        """
        state = peek(conversation_id)
        if state is None:
            return False
        active = state.active
        if active is None or active.task is None or active.task.done():
            return False
        active.interrupted = True
        state.paused = True
        active.task.cancel()
        log.debug("Interrupted turn for conversation %s", conversation_id)
        return True

    def cancel_turn(self, conversation_id: str) -> None:
        """Cancel and discard a running turn and drop the pending queue (used when
        the conversation is deleted).

        The whole state is dropped here; the task's ``finally`` release is
        ownership-checked, so a racing start's fresh state is never evicted.
        """
        state = _STATES.pop(conversation_id, None)
        if state is None:
            return
        active = state.active
        if active is not None and active.task is not None and not active.task.done():
            active.discarded = True
            active.task.cancel()
            log.debug("Cancelled turn for conversation %s", conversation_id)
        state.queue.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _maybe_advance(self, conversation_id: str) -> None:
        """Start the next pending message if the conversation is idle + unpaused;
        release the conversation's state when there is nothing left to hold."""
        state = peek(conversation_id)
        if state is None:
            return
        if state.active is not None or state.paused or not state.queue or is_stopping():
            # Stopping: a cancelled turn's end must not start the next one
            # mid-teardown (``turn_state.stop_all_turns``); the queue is held.
            evict_if_idle(conversation_id)
            return
        message = state.queue.pop(0)
        try:
            started = await self._begin_turn(conversation_id, message)
        except TurnsStopping:
            state.queue.insert(0, message)
            state.paused = True
        except Exception:
            log.exception("auto-advance turn failed for conversation %s", conversation_id)
            # Re-insert the head and pause so the message is neither lost nor retried in
            # a spin; the owner resumes (send) after fixing the cause (spec chat "Hold
            # a queued turn that fails to start until the chat writes again" — a queued
            # message must not vanish).
            state.queue.insert(0, message)
            state.paused = True
            error = TurnError(code="INTERNAL_ERROR", message="failed to start queued turn")
            if message.on_start is not None:
                # A channel has no queue chips to look at: hand its renderer a
                # stream that carries the failure and ends, so the chat hears it.
                failed: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
                failed.put_nowait(error)
                failed.put_nowait(None)
                message.on_start(failed)
        else:
            if not started:
                # Refused (the session is open elsewhere): the message is not
                # retried; the ones behind it each get their own answer.
                await self._maybe_advance(conversation_id)

    async def _begin_turn(
        self,
        conversation_id: str,
        message: PendingMessage,
    ) -> bool:
        """Reserve the slot, build the adapter, name and touch the conversation,
        spawn the turn task. Callers guarantee no turn is currently active.

        The message's text and attachments (channel media) are handed to the
        adapter as the turn's input; the title hint is what the
        placeholder-title rule names the conversation from instead of the raw text.

        Raises ``TurnsStopping`` once the daemon has begun stopping its turns —
        checked on entry and again just before the conversation is touched, so
        a start that raced ``stop_all_turns`` changes nothing and spawns nothing.

        Returns ``True`` when the turn started and ``False`` when it was refused
        because its native session is open outside the daemon: the message's
        renderer (``on_start``) is handed a stream that carries the refusal and
        ends. A message with no renderer raises ``SessionInUse`` instead."""
        if is_stopping():
            raise TurnsStopping(conversation_id)
        state = state_for(conversation_id)
        primary_queue: asyncio.Queue[AgentEvent | None] | None = (
            asyncio.Queue() if message.on_start is not None else None
        )
        active = ActiveTurn(primary_queue=primary_queue)
        # Reserve synchronously — no ``await`` before this assignment.
        state.active = active
        # The turn's token, minted before the adapter is built: the provider puts
        # it into the agent process's environment (``COFFER_TURN_TOKEN``) so the
        # agent's ``coffer__ask`` calls resolve to this turn.
        turn = questions.register_turn(conversation_id)
        try:
            conv = await self._chat.get_conversation(conversation_id)
            session_id = conv.agent_config.session_id
            if (
                session_id
                and self._session_in_use is not None
                and await self._session_in_use.in_use(session_id)
            ):
                raise SessionInUse(session_id)
            provider = self._registry.get(conv.agent_key)
            adapter = await provider.build_adapter(conversation_id)
            if is_stopping():
                raise TurnsStopping(conversation_id)
            await self._chat.begin_turn(
                conversation_id, text=message.text, title_hint=message.title_hint
            )
        except BaseException as exc:
            # Anything failed before the task spawned — release the reservation.
            questions.release_turn(turn)
            if state.active is active:
                state.active = None
            if primary_queue is not None:
                primary_queue.put_nowait(None)
            if isinstance(exc, SessionInUse) and message.on_start is not None:
                refused: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
                refused.put_nowait(TurnError(code=SESSION_IN_USE, message=SESSION_IN_USE_MESSAGE))
                refused.put_nowait(None)
                message.on_start(refused)
                return False
            raise

        # Bound around the spawn: the turn task and whatever ``on_start`` spawns
        # to render it copy the turn's correlation ids into every record.
        with correlation.turn(conversation_id):
            task = spawn(
                run_turn_task(
                    conversation_id=conversation_id,
                    active=active,
                    adapter=adapter,
                    chat=self._chat,
                    prompt=message.text,
                    attachments=message.attachments,
                    idle_timeout=self._idle_timeout,
                    turn=turn,
                ),
                name=f"turn:{conversation_id}",
            )
            active.task = task
            task.add_done_callback(self._advance_callback(conversation_id))
            if message.on_start is not None and primary_queue is not None:
                # After the task exists, so a renderer that stops the turn finds it.
                message.on_start(primary_queue)
        return True

    def _advance_callback(self, conversation_id: str) -> Callable[[asyncio.Task[None]], None]:
        def _cb(_task: asyncio.Task[None]) -> None:
            advance = spawn(self._maybe_advance(conversation_id), name="turn-advance")
            self._bg_tasks.add(advance)
            advance.add_done_callback(self._bg_tasks.discard)

        return _cb


__all__ = [
    "TurnOrchestrator",
    "TurnState",
    "active_turns",
    "clear_active_turns",
    "held_conversations",
]
