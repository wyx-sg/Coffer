"""Persistence helpers for the turn orchestrator.

Split out of ``turn_orchestrator.py`` (file-size limit): the end-of-turn
finalize/audit write and the cancel-raced placeholder recovery. Both are pure
application-layer helpers over the ``ChatService`` / ``AuditService`` ports.
"""

from __future__ import annotations

import asyncio
import logging

from coffer.application.audit_service import AuditService
from coffer.application.chat.service import ChatService
from coffer.domain.audit import AuditEventType
from coffer.domain.chat.events import TurnDone, TurnError
from coffer.domain.chat.message import (
    ContentBlock,
    Message,
    Role,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

log = logging.getLogger(__name__)


async def finalize_assistant_message(
    *,
    chat: ChatService,
    audit: AuditService,
    conversation_id: str,
    message_id: str | None,
    model_id: str | None,
    text_parts: list[str],
    tool_use_blocks: list[ToolUseBlock],
    tool_result_blocks: list[ToolResultBlock],
    final_done: TurnDone | None,
    error_event: TurnError | None,
) -> None:
    """Finalise the streaming placeholder with its content/status + audit it.

    Finalising the same placeholder row is idempotent, so a finalise that
    races a cancellation cannot leave two assistant messages. When
    ``message_id`` is ``None`` (the placeholder write itself failed or was
    cancelled before committing) the message is appended directly instead,
    so the turn still leaves a persisted record and an audit entry.
    """
    content: list[ContentBlock] = []
    if text_parts:
        content.append(TextBlock(text="".join(text_parts)))
    content.extend(tool_use_blocks)
    content.extend(tool_result_blocks)

    status = "failed" if error_event is not None else "complete"
    prompt_tokens = final_done.prompt_tokens if final_done is not None else None
    completion_tokens = final_done.completion_tokens if final_done is not None else None

    try:
        if message_id is not None:
            await chat.finalize_message(
                conversation_id,
                message_id,
                content=content,
                status=status,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        else:
            await chat.append_message(
                conversation_id,
                role=Role.ASSISTANT,
                content=content,
                status=status,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
    except Exception:
        log.exception("Failed to finalize assistant message for conversation %s", conversation_id)

    try:
        await audit.record(
            AuditEventType.CHAT_TURN_COMPLETED.value,
            actor="agent",
            details={
                "conversation_id": conversation_id,
                "model_id": model_id,
                "status": status,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )
    except Exception:
        log.exception("Failed to emit audit event for conversation %s", conversation_id)


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


__all__ = ["finalize_assistant_message", "recover_placeholder_id"]
