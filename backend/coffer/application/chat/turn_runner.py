"""The detached turn task — drive the adapter, publish events, persist the result.

Extracted from ``TurnOrchestrator`` so the orchestrator file stays focused. The
task publishes every ``AgentEvent`` to the conversation bus (so any number of web
subscribers observe it) and, when the turn was started with a dedicated queue
(a channel renderer's, or ``start_turn``'s), to that queue too — ending it with
a ``None`` sentinel. Every way a turn ends short keeps what it streamed (spec
chat "Keep partial output when a turn is interrupted or fails"): a user
interrupt finalises the partial as complete; an adapter stream that stops
without a terminal event is reported as ``stream_ended`` and the partial marked
failed; a daemon shutdown cancelling the task marks it failed too. Only a
delete (``ActiveTurn.discarded``) throws the turn away. While streaming, the
reply so far is flushed onto the ``streaming`` row (throttled —
``PartialFlusher``) so a daemon that dies outright leaves the text for the
startup sweep.

The idle watchdog
-----------------
An agent process can wedge without dying — a hung tool, a network call that
never returns, a CLI waiting on a prompt nobody will answer. Nothing upstream
bounds that: the adapters wait for the next message forever. So the task
itself keeps time between events: if none arrives for ``idle_timeout`` seconds
the turn is cancelled with a ``turn_timeout`` error, which runs the adapter's
own cancellation path (interrupt + disconnect / close — the backend subprocess
is terminated there) and keeps whatever text was streamed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence

from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_persistence import (
    DEFAULT_PARTIAL_FLUSH_SECONDS,
    PartialFlusher,
    TurnContent,
    finalize_assistant_message,
    recover_placeholder_id,
)
from coffer.application.chat.turn_state import ActiveTurn, release_active
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import (
    STREAM_ENDED,
    STREAM_ENDED_MESSAGE,
    TURN_TIMEOUT,
    AgentEvent,
    TurnDone,
    TurnError,
)
from coffer.domain.chat.message import AttachmentBlock, Message, Role

log = logging.getLogger(__name__)

#: Default for the idle watchdog. Five minutes is longer than any single tool
#: call a coding agent legitimately makes, and short enough that a wedged turn
#: does not hold a conversation (and its subprocess) for an afternoon. The
#: daemon reads ``COFFER_TURN_IDLE_TIMEOUT_SECONDS`` to change it (``0``
#: disables the watchdog).
DEFAULT_TURN_IDLE_TIMEOUT_SECONDS = 300.0

#: How much of a conversation a turn is given. The adapters resume the agent's
#: own session, which already holds the conversation; the history here is what
#: a fresh session or a path-native agent gets as context, and the most recent
#: rows are the ones that matter for it. A conversation of thousands of
#: messages must not be loaded whole on every turn.
HISTORY_LIMIT = 200

#: ``TurnError.code`` when the daemon itself cancels a turn on its way down
#: (neither a user interrupt nor a delete); the partial is kept, marked failed —
#: the outcome the startup sweep gives a turn a crash cut short.
DAEMON_STOPPED = "daemon_stopped"
DAEMON_STOPPED_MESSAGE = "Coffer stopped before the turn finished"


def _attachments_from_history(history: Sequence[Message]) -> list[Attachment]:
    """Re-materialise this turn's attachments from the persisted history.

    The current user message (the last ``Role.USER`` row — it was persisted before
    ``history`` was fetched) is the single source of truth for the turn's channel media:
    map each of its ``AttachmentBlock`` references back to an ``Attachment`` VO the
    adapter materialises. Reading them back from history (rather than threading a param
    down) means the reference survives a daemon restart and stays consistent with what
    the web Chat page shows (see "Re-materialise attachments from persisted
    history")."""
    for msg in reversed(history):
        if msg.role is Role.USER:
            return [
                Attachment(path=b.path, mime=b.mime, filename=b.filename)
                for b in msg.content
                if isinstance(b, AttachmentBlock)
            ]
    return []


async def _next_event(events: AsyncIterator[AgentEvent], idle_timeout: float | None) -> AgentEvent:
    """The adapter's next event, or ``TimeoutError`` after ``idle_timeout``
    seconds of silence.

    The timeout cancels the wait *inside* the adapter's generator, so the
    adapter's own ``CancelledError`` handling runs — the same path a user
    interrupt takes — before the ``TimeoutError`` surfaces here. An external
    cancellation (interrupt, delete) still arrives as ``CancelledError``.
    """
    if idle_timeout is None:
        return await events.__anext__()
    async with asyncio.timeout(idle_timeout):
        return await events.__anext__()


async def run_turn_task(
    *,
    conversation_id: str,
    active: ActiveTurn,
    adapter: AgentAdapter,
    chat: ChatService,
    idle_timeout: float | None = DEFAULT_TURN_IDLE_TIMEOUT_SECONDS,
    flush_interval: float | None = DEFAULT_PARTIAL_FLUSH_SECONDS,
) -> None:
    """Async task body: drive the adapter, publish events, persist the result.

    The turn's attachments (channel media) are derived from ``history``'s last user
    message (see "Re-materialise attachments from persisted history") and handed to the
    adapter, which materialises them in its own native shape."""
    bus = active.bus

    def emit(event: AgentEvent) -> None:
        bus.publish(event)
        if active.primary_queue is not None:
            active.primary_queue.put_nowait(event)

    # Text and tool blocks in the order the turn emitted them.
    content = TurnContent()
    flusher = PartialFlusher(chat, content, interval=flush_interval)
    final_done: TurnDone | None = None
    error_event: TurnError | None = None
    # An adapter may expose the resolved model id so the assistant message can
    # record it. Other adapters need not; best-effort read.
    model_id: str | None = getattr(adapter, "model_id", None)
    placeholder_id: str | None = None
    append_task: asyncio.Task[Message] | None = None

    try:
        history = await chat.list_messages(conversation_id, limit=HISTORY_LIMIT)
        turn_attachments = _attachments_from_history(history)
        # Write a ``streaming`` placeholder assistant row BEFORE the first event. A
        # daemon crash mid-turn then leaves a row the startup sweep flips to ``failed``
        # (see "Sweep streaming rows left by a crashed daemon"), carrying whatever the
        # last partial flush wrote. It is finalised in place on completion (one row,
        # no dup). The write runs as a shielded task: a
        # cancellation landing between the row's commit and the id assignment leaves the
        # task running, and the CancelledError handler recovers the id.
        append_task = asyncio.create_task(
            chat.append_message(
                conversation_id,
                role=Role.ASSISTANT,
                content=[],
                status="streaming",
                model_id=model_id,
            )
        )
        placeholder_id = (await asyncio.shield(append_task)).id

        events = (await adapter.run_turn(history=history, attachments=turn_attachments)).__aiter__()
        while True:
            try:
                event = await _next_event(events, idle_timeout)
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
            emit(event)
            content.add(event)
            await flusher.after(event, placeholder_id)
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
            # TurnStarted / QueueChanged: forwarded only, not message content.

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

        await finalize_assistant_message(
            chat=chat,
            conversation_id=conversation_id,
            message_id=placeholder_id,
            model_id=model_id,
            content=content,
            final_done=final_done,
            error_event=error_event,
        )
    except asyncio.CancelledError:
        # The cancel may have landed while the placeholder write was still in
        # flight; recover the committed row's id so it is not orphaned.
        placeholder_id = await recover_placeholder_id(placeholder_id, append_task)
        if active.interrupted:
            # User interrupt: keep whatever the agent produced. Emit a terminal
            # event and finalise the partial message. The finalise is shielded so
            # a second cancellation (e.g. the conversation is deleted while this
            # interrupt is mid-write) cannot abort the write half-done.
            done = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="interrupted")
            emit(done)
            await asyncio.shield(
                finalize_assistant_message(
                    chat=chat,
                    conversation_id=conversation_id,
                    message_id=placeholder_id,
                    model_id=model_id,
                    content=content,
                    final_done=done,
                    error_event=None,
                )
            )
            # Cancellation handled — do NOT re-raise.
        elif active.discarded:
            # Conversation deleted: discard the partial turn entirely — remove the
            # placeholder so no orphan streaming row remains.
            if placeholder_id is not None:
                await asyncio.shield(chat.delete_message(placeholder_id))
            log.debug("Turn for conversation %s cancelled and discarded", conversation_id)
            raise
        else:
            # Nobody asked for this cancellation: the daemon is going down. Keep the
            # partial, marked failed — what the startup sweep would give it.
            error_event = TurnError(code=DAEMON_STOPPED, message=DAEMON_STOPPED_MESSAGE)
            emit(error_event)
            await asyncio.shield(
                finalize_assistant_message(
                    chat=chat,
                    conversation_id=conversation_id,
                    message_id=placeholder_id,
                    model_id=model_id,
                    content=content,
                    final_done=None,
                    error_event=error_event,
                )
            )
            log.info("Turn for conversation %s stopped by shutdown; partial kept", conversation_id)
            raise
    except Exception as exc:
        log.exception("Unexpected error in turn task for conversation %s", conversation_id)
        error_event = TurnError(code="INTERNAL_ERROR", message=str(exc))
        emit(error_event)
        # placeholder_id may be None when the placeholder write itself failed;
        # _finalize falls back to appending a failed row so the turn still leaves a
        # persisted trace.
        await finalize_assistant_message(
            chat=chat,
            conversation_id=conversation_id,
            message_id=placeholder_id,
            model_id=model_id,
            content=content,
            final_done=final_done,
            error_event=error_event,
        )
    finally:
        # Ownership-checked release — only our own entry, so a racing start that
        # registered a fresh turn is not lost.
        release_active(conversation_id, active)
        bus.end_turn()
        # Close the dedicated queue so its renderer never hangs.
        if active.primary_queue is not None:
            active.primary_queue.put_nowait(None)
