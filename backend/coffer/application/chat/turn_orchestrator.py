"""TurnOrchestrator — runs one turn per conversation, agent-agnostically.

The orchestrator is pure chat-platform plumbing: it knows the agent-provider
registry and nothing about any specific agent. For each turn it asks the
registry for the conversation's provider, has the provider build a configured
adapter, drives ``adapter.run_turn(history, approvals)``, streams the events,
and persists the assistant message.

Responsibilities
----------------
- ``start_turn``: enforce one-in-flight-turn-per-conversation, build the
  agent adapter (which may raise ``NoModelConfigured`` for the built-in agent),
  persist the user message, spawn a detached turn task, return the event queue.
- The turn task: drive the adapter, forward every ``AgentEvent`` onto the
  queue, accumulate the assistant message, persist it, emit the
  ``chat_turn_completed`` audit event, and signal end-of-stream.
- ``interrupt_turn``: stop a running turn but keep its partial output.
- ``cancel_turn``: stop and discard a running turn (used on conversation delete).
- ``submit_approval``: deliver a human approval decision to a waiting turn.
- ``sweep_streaming_messages``: startup recovery for crash-left ``streaming`` rows.

Architecture notes
-------------------
- ``_ACTIVE_TURNS`` (module-level) maps ``conversation_id`` → ``_ActiveTurn``.
  The entry is registered synchronously, right after the ``TurnInProgress``
  guard, so two concurrent ``start_turn`` calls cannot both pass the guard.
- The per-turn ``asyncio.Queue`` uses ``None`` as the end-of-stream sentinel.
- A client disconnect cancels only the queue drain, not the turn task, so the
  assistant message is still persisted (research.md §7).
- Interruption vs. deletion: both cancel the task; ``_ActiveTurn.interrupted``
  tells the task's ``CancelledError`` handler whether to persist the partial
  message (interrupt) or discard it (delete).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from coffer.application.audit_service import AuditService
from coffer.application.chat.approvals import ApprovalChannel
from coffer.application.chat.ports import AgentAdapter, ApprovalDecision
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService, MessageRepo
from coffer.application.chat.turn_persistence import (
    finalize_assistant_message,
    recover_placeholder_id,
)
from coffer.domain.chat.events import (
    AgentEvent,
    ApprovalRequest,
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
from coffer.domain.errors import ApprovalNotFound, TurnInProgress

log = logging.getLogger(__name__)


@dataclass
class _ActiveTurn:
    """In-process record of one conversation's in-flight turn."""

    queue: asyncio.Queue[AgentEvent | None]
    approvals: ApprovalChannel
    task: asyncio.Task[None] | None = None
    interrupted: bool = field(default=False)


# Module-level registry of live turns: conversation_id → _ActiveTurn.
# A turn queue yields AgentEvent objects, then a ``None`` end-of-stream sentinel.
_ACTIVE_TURNS: dict[str, _ActiveTurn] = {}


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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_turn(
        self, conversation_id: str, user_text: str
    ) -> asyncio.Queue[AgentEvent | None]:
        """Start a new turn for the conversation.

        1. Raises ``TurnInProgress`` if a turn is already active.
        2. Resolves the conversation's agent provider and builds its adapter —
           the built-in provider raises ``NoModelConfigured`` here when no model
           is configured; any provider may raise a domain error.
        3. Persists the user message.
        4. Spawns a detached turn task and returns its event queue.

        The queue yields ``AgentEvent`` objects and finally a ``None`` sentinel.
        """
        if conversation_id in _ACTIVE_TURNS:
            raise TurnInProgress(conversation_id)
        # Reserve the slot synchronously — there is no ``await`` between the
        # guard above and this insert, so a concurrent ``start_turn`` for the
        # same conversation cannot also pass the guard.
        active = _ActiveTurn(queue=asyncio.Queue(), approvals=ApprovalChannel())
        _ACTIVE_TURNS[conversation_id] = active

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
            raise

        task = asyncio.create_task(
            self._run_turn(conversation_id, active, adapter),
            name=f"turn:{conversation_id}",
        )
        active.task = task
        return active.queue

    def interrupt_turn(self, conversation_id: str) -> None:
        """Stop a running turn, keeping whatever it produced so far.

        The turn task is cancelled; its ``CancelledError`` handler persists the
        partial assistant message. A no-op when no turn is in flight.
        """
        active = _ACTIVE_TURNS.get(conversation_id)
        if active is not None and active.task is not None and not active.task.done():
            active.interrupted = True
            active.task.cancel()
            log.debug("Interrupted turn for conversation %s", conversation_id)

    def cancel_turn(self, conversation_id: str) -> None:
        """Cancel a running turn and discard it (used when the conversation is
        deleted). Unlike ``interrupt_turn``, no partial message is persisted —
        the conversation is being removed anyway.

        Does NOT pop the entry from ``_ACTIVE_TURNS``; the task's ``finally``
        performs an ownership-checked removal so a racing ``start_turn`` cannot
        have its fresh entry evicted.
        """
        active = _ACTIVE_TURNS.get(conversation_id)
        if active is not None and active.task is not None and not active.task.done():
            active.task.cancel()
            log.debug("Cancelled turn for conversation %s", conversation_id)

    def submit_approval(
        self, conversation_id: str, request_id: str, decision: ApprovalDecision
    ) -> None:
        """Deliver a human approval decision to the conversation's in-flight turn.

        Raises ``ApprovalNotFound`` when the conversation has no active turn, or
        the turn has no pending request matching ``request_id``.
        """
        active = _ACTIVE_TURNS.get(conversation_id)
        if active is None:
            raise ApprovalNotFound(request_id)
        active.approvals.resolve(request_id, decision)

    @staticmethod
    async def sweep_streaming_messages(message_repo: MessageRepo) -> int:
        """Flip any lingering ``status='streaming'`` rows to ``'failed'``.

        Called once at daemon startup to recover from a prior crash. Returns the
        number of rows flipped.
        """
        return await message_repo.sweep_streaming()

    # ------------------------------------------------------------------
    # Internal turn task
    # ------------------------------------------------------------------

    async def _run_turn(
        self,
        conversation_id: str,
        active: _ActiveTurn,
        adapter: AgentAdapter,
    ) -> None:
        """Async task body: drive the adapter, stream events, persist the result."""
        queue = active.queue
        text_parts: list[str] = []
        tool_use_blocks: list[ToolUseBlock] = []
        tool_result_blocks: list[ToolResultBlock] = []
        final_done: TurnDone | None = None
        error_event: TurnError | None = None
        # The built-in adapter exposes the resolved model id so the assistant
        # message can record it. Other adapters need not; best-effort read.
        model_id: str | None = getattr(adapter, "model_id", None)
        # Id of the streaming placeholder row; None until it is written.
        placeholder_id: str | None = None
        append_task: asyncio.Task[Message] | None = None

        try:
            history = await self._chat.list_messages(conversation_id)
            # Write a ``streaming`` placeholder assistant row BEFORE the first
            # event. A daemon crash mid-turn then leaves a row the startup sweep
            # flips to ``failed`` (FR-022), rather than a silently-missing
            # reply. It is finalised in place on completion (one row, no dup).
            # The write runs as a shielded task: a cancellation landing between
            # the row's commit and the id assignment leaves the task running,
            # and the CancelledError handler recovers the id from it so the
            # committed row is finalized/deleted rather than orphaned.
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

            async for event in await adapter.run_turn(history=history, approvals=active.approvals):
                if isinstance(event, ApprovalRequest):
                    # Register before forwarding so a decision posted the moment
                    # the client sees the event is accepted, not rejected for a
                    # not-yet-awaited request (see ApprovalChannel.register).
                    active.approvals.register(event.request_id)
                await queue.put(event)
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
                # TurnStarted / ApprovalRequest: forwarded only, not message content.

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
            # The cancel may have landed while the placeholder write was still
            # in flight; recover the committed row's id so it is not orphaned.
            placeholder_id = await recover_placeholder_id(placeholder_id, append_task)
            if active.interrupted:
                # User interrupt: keep whatever the agent produced. Emit a
                # terminal event and finalise the partial assistant message.
                # The finalise is shielded so a second cancellation (e.g. the
                # conversation is deleted while this interrupt is mid-write)
                # cannot abort the partial-message write half-done.
                done = TurnDone(
                    prompt_tokens=None, completion_tokens=None, stop_reason="interrupted"
                )
                queue.put_nowait(done)
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
                # Conversation deleted: discard the partial turn entirely —
                # remove the placeholder so no orphan streaming row remains.
                if placeholder_id is not None:
                    await asyncio.shield(self._chat.delete_message(placeholder_id))
                log.debug("Turn for conversation %s cancelled and discarded", conversation_id)
                raise
        except Exception as exc:
            log.exception("Unexpected error in turn task for conversation %s", conversation_id)
            error_event = TurnError(code="INTERNAL_ERROR", message=str(exc))
            await queue.put(error_event)
            # placeholder_id may be None when the placeholder write itself
            # failed; _finalize falls back to appending a failed row so the
            # turn still leaves a persisted + audited trace.
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
            # start_turn that registered a fresh entry is not lost.
            if _ACTIVE_TURNS.get(conversation_id) is active:
                del _ACTIVE_TURNS[conversation_id]
            # Always signal end-of-stream so the SSE consumer never hangs, even
            # when CancelledError propagates. put_nowait on the unbounded queue
            # never awaits and so cannot itself be cancelled mid-finally.
            queue.put_nowait(None)

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
    """Clear all active turns (test teardown only)."""
    _ACTIVE_TURNS.clear()
