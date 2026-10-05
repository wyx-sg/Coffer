"""The detached turn task — drive the adapter and publish its events.

Extracted from ``TurnOrchestrator`` so the orchestrator file stays focused. The
task publishes every ``AgentEvent`` to the turn's dedicated queue (a channel
renderer's) — ending it with a ``None`` sentinel. Coffer keeps no copy of the reply: the
agent's own session holds the conversation, so a turn that ends short has
nothing to persist. A user interrupt ends the turn as ``interrupted``; an
adapter stream that stops without a terminal event is reported as
``stream_ended``; a daemon shutdown cancelling the task reports
``daemon_stopped``. Only a delete (``ActiveTurn.discarded``) ends it silently.
A turn ends exactly once: a cancel landing after its terminal event emits
nothing more. The conversation's ``updated_at`` is bumped when the turn ends.

The idle watchdog
-----------------
An agent process can wedge without dying — a hung tool, a network call that
never returns, a CLI waiting on a prompt nobody will answer. Nothing upstream
bounds that: the adapters wait for the next message forever. So the task
itself keeps time between events: if none arrives for ``idle_timeout`` seconds
the turn is cancelled with a ``turn_timeout`` error, which runs the adapter's
own cancellation path (interrupt + disconnect / close — the backend subprocess
is terminated there).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence

from coffer.application.chat import questions
from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_state import ActiveTurn, release_active
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import (
    STREAM_ENDED,
    STREAM_ENDED_MESSAGE,
    TURN_TIMEOUT,
    AgentEvent,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)

log = logging.getLogger(__name__)

#: Default for the idle watchdog. Five minutes is longer than any single tool
#: call a coding agent legitimately makes, and short enough that a wedged turn
#: does not hold a conversation (and its subprocess) for an afternoon. The
#: daemon reads ``COFFER_TURN_IDLE_TIMEOUT_SECONDS`` to change it (``0``
#: disables the watchdog).
DEFAULT_TURN_IDLE_TIMEOUT_SECONDS = 300.0

#: ``TurnError.code`` when the daemon itself cancels a turn on its way down
#: (neither a user interrupt nor a delete).
DAEMON_STOPPED = "daemon_stopped"
DAEMON_STOPPED_MESSAGE = "Coffer stopped before the turn finished"


def _is_ask_tool(name: str) -> bool:
    """Claude Code's own dialog tool, or ``coffer__ask`` under whatever
    server prefix the agent gives it: both are rendered as the question block,
    not as a tool card."""
    return name == "AskUserQuestion" or name.endswith("coffer__ask")


def _reported_model(adapter: AgentAdapter) -> str | None:
    """The model the adapter says the turn ran on; optional, read best-effort."""
    try:
        model = getattr(adapter, "model_id", None)
    except Exception:
        return None
    return model if isinstance(model, str) and model else None


class _IdleWatch:
    """The idle watchdog's deadline, which a pending question for the owner
    suspends: silence while the turn waits on a person is not a wedge (the
    question has its own 24-hour expiry)."""

    def __init__(self, idle_timeout: float | None) -> None:
        self.idle_timeout = idle_timeout
        self.paused = False
        self.timeout: asyncio.Timeout | None = None

    def waiting(self, waiting_on_owner: bool) -> None:
        """The turn started, or stopped, waiting on the owner."""
        self.paused = waiting_on_owner
        if self.timeout is not None and self.idle_timeout is not None:
            when = (
                None if waiting_on_owner else asyncio.get_running_loop().time() + self.idle_timeout
            )
            self.timeout.reschedule(when)


async def _next_event(events: AsyncIterator[AgentEvent], watch: _IdleWatch) -> AgentEvent:
    """The adapter's next event, or ``TimeoutError`` after ``idle_timeout``
    seconds of silence (none while the turn waits on the owner).

    The timeout cancels the wait *inside* the adapter's generator, so the
    adapter's own ``CancelledError`` handling runs — the same path a user
    interrupt takes — before the ``TimeoutError`` surfaces here. An external
    cancellation (interrupt, delete) still arrives as ``CancelledError``.
    """
    if watch.idle_timeout is None:
        return await events.__anext__()
    async with asyncio.timeout(None if watch.paused else watch.idle_timeout) as timeout:
        watch.timeout = timeout
        try:
            return await events.__anext__()
        finally:
            watch.timeout = None


async def run_turn_task(
    *,
    conversation_id: str,
    active: ActiveTurn,
    adapter: AgentAdapter,
    chat: ChatService,
    prompt: str,
    attachments: Sequence[Attachment] = (),
    idle_timeout: float | None = DEFAULT_TURN_IDLE_TIMEOUT_SECONDS,
    turn: questions.TurnContext | None = None,
) -> None:
    """Async task body: drive the adapter and publish its events.

    ``prompt`` and ``attachments`` (channel media) are the turn's input; the
    adapter materialises the attachments in its own native shape."""

    def emit(event: AgentEvent) -> None:
        if active.primary_queue is not None:
            active.primary_queue.put_nowait(event)

    final_done: TurnDone | None = None
    error_event: TurnError | None = None

    ask_tool_ids: set[str] = set()
    watch = _IdleWatch(idle_timeout)
    if turn is not None:
        turn.on_waiting = watch.waiting

    async def on_question(event: AgentEvent) -> None:
        # A question the agent raised (or that closed): in the channel
        # renderer's queue.
        emit(event)

    async def finish() -> None:
        if turn is not None:
            # The turn is over: whatever it still waits on can no longer be
            # answered, and the reply must say so.
            await questions.close_turn(turn)
        try:
            await chat.end_turn(conversation_id)
        except Exception:
            log.warning("Could not bump conversation %s after its turn", conversation_id)

    try:
        if turn is not None:
            turn.on_event = on_question

        events = (await adapter.run_turn(prompt, attachments)).__aiter__()
        while True:
            try:
                event = await _next_event(events, watch)
            except StopAsyncIteration:
                break
            except TimeoutError:
                error_event = TurnError(
                    code=TURN_TIMEOUT,
                    message=(
                        f"the agent produced nothing for {idle_timeout:g}s; "
                        "the turn was cancelled and the agent process stopped"
                    ),
                )
                log.warning(
                    "Turn for conversation %s idle for %ss — cancelled (%s)",
                    conversation_id,
                    idle_timeout,
                    TURN_TIMEOUT,
                )
                emit(error_event)
                break
            if isinstance(event, ToolCall) and _is_ask_tool(event.tool_name):
                ask_tool_ids.add(event.tool_use_id)
                continue
            if isinstance(event, ToolResult) and event.tool_use_id in ask_tool_ids:
                continue
            emit(event)
            if isinstance(event, TurnDone):
                final_done = event
            elif isinstance(event, TurnError):
                error_event = event
                log.warning(
                    "Turn for conversation %s ended with %s: %s",
                    conversation_id,
                    event.code,
                    event.message,
                )

        if final_done is None and error_event is None:
            # The stream ran out with no terminal event: the agent died or lost its
            # connection mid-turn. Detected here, agent-agnostically, so an adapter
            # that does not synthesise it cannot pass a cut reply off as complete.
            error_event = TurnError(code=STREAM_ENDED, message=STREAM_ENDED_MESSAGE)
            log.warning(
                "Turn for conversation %s ended without a terminal event (%s)",
                conversation_id,
                STREAM_ENDED,
            )
            emit(error_event)

        if final_done is not None:
            # Coffer stores no reply to carry the model, so the log line does.
            log.info(
                "Turn for conversation %s completed (model=%s)",
                conversation_id,
                _reported_model(adapter),
            )
        await finish()
    except asyncio.CancelledError:
        if active.discarded:
            # Conversation deleted: nothing to finish, nothing to report.
            log.debug("Turn for conversation %s cancelled and discarded", conversation_id)
            raise
        # A terminal event (TurnDone / TurnError) already out means the turn has
        # ended — the cancel landed after it: the turn ends as that event said,
        # with no second terminal.
        if final_done is None and error_event is None:
            if active.interrupted:
                # User interrupt.
                final_done = TurnDone(
                    prompt_tokens=None, completion_tokens=None, stop_reason="interrupted"
                )
                emit(final_done)
            else:
                # Nobody asked for this cancellation: the daemon is going down.
                error_event = TurnError(code=DAEMON_STOPPED, message=DAEMON_STOPPED_MESSAGE)
                emit(error_event)
        # Shielded so a second cancellation (e.g. the conversation is deleted while
        # an interrupt is mid-write) cannot abort the finish half-done.
        await asyncio.shield(finish())
        if not active.interrupted:
            log.info("Turn for conversation %s stopped by shutdown", conversation_id)
            raise
        # User interrupt handled — do NOT re-raise.
    except Exception as exc:
        log.exception("Unexpected error in turn task for conversation %s", conversation_id)
        error_event = TurnError(code="INTERNAL_ERROR", message=str(exc))
        emit(error_event)
        await finish()
    finally:
        if turn is not None:
            questions.release_turn(turn)
        # Ownership-checked release — only our own entry, so a racing start that
        # registered a fresh turn is not lost.
        release_active(conversation_id, active)
        # Close the dedicated queue so its renderer never hangs.
        if active.primary_queue is not None:
            active.primary_queue.put_nowait(None)
