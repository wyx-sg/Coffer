"""The detached turn task — drive the adapter, publish events, persist the result.

Extracted from ``TurnOrchestrator`` so the orchestrator file stays focused. The
task publishes every ``AgentEvent`` to the conversation bus (so any number of web
subscribers observe it) and, when a ``start_turn`` caller supplied a dedicated
queue (the channel renderer), to that queue too — ending it with a ``None``
sentinel. The cancellation/shielding semantics are unchanged: a user interrupt
keeps the partial assistant message; a delete discards it.
"""

from __future__ import annotations

import asyncio
import logging

from coffer.application.audit_service import AuditService
from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_persistence import (
    finalize_assistant_message,
    recover_placeholder_id,
)
from coffer.application.chat.turn_state import _ACTIVE_TURNS, _ActiveTurn
from coffer.domain.chat.events import (
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)
from coffer.domain.chat.message import Message, Role, ToolResultBlock, ToolUseBlock

log = logging.getLogger(__name__)


async def run_turn_task(
    *,
    conversation_id: str,
    active: _ActiveTurn,
    adapter: AgentAdapter,
    chat: ChatService,
    audit: AuditService,
) -> None:
    """Async task body: drive the adapter, publish events, persist the result."""
    bus = active.bus

    def emit(event: object) -> None:
        bus.publish(event)  # type: ignore[arg-type]
        if active.primary_queue is not None:
            active.primary_queue.put_nowait(event)  # type: ignore[arg-type]

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
        history = await chat.list_messages(conversation_id)
        # Write a ``streaming`` placeholder assistant row BEFORE the first event.
        # A daemon crash mid-turn then leaves a row the startup sweep flips to
        # ``failed`` (FR-022). It is finalised in place on completion (one row, no
        # dup). The write runs as a shielded task: a cancellation landing between
        # the row's commit and the id assignment leaves the task running, and the
        # CancelledError handler recovers the id.
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

        await finalize_assistant_message(
            chat=chat,
            audit=audit,
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
            # event and finalise the partial message. The finalise is shielded so
            # a second cancellation (e.g. the conversation is deleted while this
            # interrupt is mid-write) cannot abort the write half-done.
            done = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="interrupted")
            emit(done)
            await asyncio.shield(
                finalize_assistant_message(
                    chat=chat,
                    audit=audit,
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
            # Conversation deleted: discard the partial turn entirely — remove the
            # placeholder so no orphan streaming row remains.
            if placeholder_id is not None:
                await asyncio.shield(chat.delete_message(placeholder_id))
            log.debug("Turn for conversation %s cancelled and discarded", conversation_id)
            raise
    except Exception as exc:
        log.exception("Unexpected error in turn task for conversation %s", conversation_id)
        error_event = TurnError(code="INTERNAL_ERROR", message=str(exc))
        emit(error_event)
        # placeholder_id may be None when the placeholder write itself failed;
        # _finalize falls back to appending a failed row so the turn still leaves a
        # persisted + audited trace.
        await finalize_assistant_message(
            chat=chat,
            audit=audit,
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
        # Ownership-checked removal — only evict our own entry so a racing start
        # that registered a fresh entry is not lost.
        if _ACTIVE_TURNS.get(conversation_id) is active:
            del _ACTIVE_TURNS[conversation_id]
        bus.end_turn()
        # Close the channel's dedicated queue so its renderer never hangs.
        if active.primary_queue is not None:
            active.primary_queue.put_nowait(None)
