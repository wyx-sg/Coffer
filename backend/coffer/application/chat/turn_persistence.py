"""Persistence helpers for the turn orchestrator.

Split out of ``turn_orchestrator.py`` (file-size limit): the ordered fold of a
turn's events into content blocks, the throttled mid-turn partial flush, the
end-of-turn finalize write, and the cancel-raced placeholder recovery. All are
pure application-layer helpers over the ``ChatService`` port.
"""

from __future__ import annotations

import asyncio
import logging
import time

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

#: The flush throttle's clock and sleep; module attributes so tests can drive them.
_clock = time.monotonic
_sleep = asyncio.sleep

#: At most one mid-turn write of the partial reply per this many seconds. A
#: daemon that dies mid-turn loses no more than about this much of the reply —
#: a trailing write catches text streamed just before a quiet stretch — and a
#: turn streaming hundreds of tokens a second still costs one row update per
#: second.
DEFAULT_PARTIAL_FLUSH_SECONDS = 1.0


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


class PartialFlusher:
    """Throttled mid-turn persistence of the reply so far (spec chat "Keep partial
    output when a turn is interrupted or fails").

    The placeholder row is written empty before the first event and finalised at
    the end; in between, the text only lived in memory, so a daemon that died
    mid-turn left the startup sweep an empty ``failed`` row. After each content
    event this writes the accumulated blocks onto the ``streaming`` row, but at
    most once per ``interval`` seconds — never per token. An event the throttle
    skips schedules one **trailing** write for when the interval is up, so text
    streamed just before a long quiet stretch (a tool run, thinking) is on disk
    within about ``interval`` rather than only when the next event arrives. Every
    write, trailing or not, lands at least ``interval`` after the previous one,
    so the bound stays one write per interval. ``close()`` cancels the trailing
    write and waits out an in-flight one; the runner calls it before finalising,
    so nothing is written after the row is final (and the store guards the write
    on ``status='streaming'`` besides). ``interval=None`` disables it.
    """

    def __init__(
        self,
        chat: ChatService,
        content: TurnContent,
        *,
        interval: float | None = DEFAULT_PARTIAL_FLUSH_SECONDS,
    ) -> None:
        self._chat = chat
        self._content = content
        self._interval = interval
        self._last = _clock()
        self._trailing: asyncio.Task[None] | None = None
        self._inflight: asyncio.Future[None] | None = None
        self._closed = False

    async def after(self, event: AgentEvent, message_id: str | None) -> None:
        """Flush if ``event`` changed the content and the interval has passed;
        otherwise make sure a trailing flush is scheduled."""
        if self._interval is None or message_id is None or self._closed:
            return
        if not isinstance(event, (TextDelta, ToolCall, ToolResult)):
            return
        wait = self._interval - (_clock() - self._last)
        if wait > 0:
            if self._trailing is None or self._trailing.done():
                self._trailing = asyncio.create_task(self._flush_later(wait, message_id))
            return
        self._cancel_trailing()
        await self._write(message_id)

    async def close(self) -> None:
        """Stop flushing: cancel a pending trailing write, wait out one in flight."""
        self._closed = True
        self._cancel_trailing()
        inflight = self._inflight
        if inflight is not None and not inflight.done():
            try:
                await asyncio.shield(inflight)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # already logged by ``_write``

    def stop(self) -> None:
        """Synchronous last resort (``finally``): no further writes are started."""
        self._closed = True
        self._cancel_trailing()

    def _cancel_trailing(self) -> None:
        if self._trailing is not None and not self._trailing.done():
            self._trailing.cancel()
        self._trailing = None

    async def _flush_later(self, delay: float, message_id: str) -> None:
        await _sleep(delay)
        if not self._closed:
            await self._write(message_id)

    async def _write(self, message_id: str) -> None:
        self._last = _clock()
        # Shielded: a cancellation mid-write leaves the (guarded) write to finish
        # rather than tearing the session down half-way; ``close`` awaits it.
        self._inflight = asyncio.ensure_future(
            self._chat.save_partial_message(message_id, self._content.blocks())
        )
        try:
            await asyncio.shield(self._inflight)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("Partial flush failed for message %s", message_id, exc_info=True)


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


__all__ = [
    "DEFAULT_PARTIAL_FLUSH_SECONDS",
    "PartialFlusher",
    "TurnContent",
    "finalize_assistant_message",
    "recover_placeholder_id",
]
