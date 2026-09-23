"""Persistence helpers for the turn orchestrator.

Split out of ``turn_orchestrator.py`` (file-size limit): the ordered fold of a
turn's events into content blocks, the end-of-turn finalize write, and the
cancel-raced placeholder recovery. All are pure application-layer helpers over
the ``ChatService`` port.
"""

from __future__ import annotations

import asyncio
import logging

from coffer.application.chat.service import ChatService
from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)
from coffer.domain.chat.message import (
    ContentBlock,
    Message,
    Role,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

log = logging.getLogger(__name__)


class TurnContent:
    """A turn's assistant content, folded from its events in emission order.

    Consecutive text deltas join into one ``TextBlock``; a tool call or result
    closes the running text, so text the agent wrote before a tool call stays
    before that call's blocks and text written after it becomes a new block
    (spec chat, "Render tool calls as cards"). Non-content events are ignored.
    """

    def __init__(self) -> None:
        self._blocks: list[ContentBlock] = []
        self._text: list[str] = []

    def add(self, event: AgentEvent) -> None:
        if isinstance(event, TextDelta):
            self._text.append(event.text)
        elif isinstance(event, ToolCall):
            self._close_text()
            self._blocks.append(
                ToolUseBlock(
                    tool_use_id=event.tool_use_id,
                    tool_name=event.tool_name,
                    tool_input=event.tool_input,
                )
            )
        elif isinstance(event, ToolResult):
            self._close_text()
            self._blocks.append(
                ToolResultBlock(
                    tool_use_id=event.tool_use_id,
                    tool_name=event.tool_name,
                    output=event.output,
                    error=event.error,
                )
            )

    def blocks(self) -> list[ContentBlock]:
        """The content so far, in emission order (the running text included)."""
        text = "".join(self._text)
        return [*self._blocks, TextBlock(text=text)] if text else list(self._blocks)

    def _close_text(self) -> None:
        text = "".join(self._text)
        if text:
            self._blocks.append(TextBlock(text=text))
        self._text = []


async def finalize_assistant_message(
    *,
    chat: ChatService,
    conversation_id: str,
    message_id: str | None,
    model_id: str | None,
    content: TurnContent,
    final_done: TurnDone | None,
    error_event: TurnError | None,
) -> None:
    """Finalise the streaming placeholder with its content/status.

    Finalising the same placeholder row is idempotent, so a finalise that
    races a cancellation cannot leave two assistant messages. When
    ``message_id`` is ``None`` (the placeholder write itself failed or was
    cancelled before committing) the message is appended directly instead,
    so the turn still leaves a persisted record.
    """
    blocks = content.blocks()
    status = "failed" if error_event is not None else "complete"
    prompt_tokens = final_done.prompt_tokens if final_done is not None else None
    completion_tokens = final_done.completion_tokens if final_done is not None else None

    try:
        if message_id is not None:
            await chat.finalize_message(
                conversation_id,
                message_id,
                content=blocks,
                status=status,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        else:
            await chat.append_message(
                conversation_id,
                role=Role.ASSISTANT,
                content=blocks,
                status=status,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
    except Exception:
        log.exception("Failed to finalize assistant message for conversation %s", conversation_id)


async def recover_placeholder_id(
    placeholder_id: str | None,
    append_task: asyncio.Task[Message] | None,
) -> str | None:
    """Recover the placeholder row id when a cancel raced the shielded write.

    The placeholder ``append_message`` runs as a shielded task; a cancellation
    delivered while awaiting it leaves the write running with ``placeholder_id``
    still ``None``. Awaiting the (shielded) task here recovers the committed
    row's id so it can be finalized or deleted instead of orphaned at
    ``status='streaming'``. Returns ``None`` when the write never committed.
    """
    if placeholder_id is not None or append_task is None:
        return placeholder_id
    try:
        return (await asyncio.shield(append_task)).id
    except BaseException:
        return None


__all__ = ["TurnContent", "finalize_assistant_message", "recover_placeholder_id"]
