"""Turn-event rendering for channels: progress, approvals, final reply.

Consumes one turn's event queue and turns it into IM traffic, strategy
selected from the adapter's declared capabilities (never its type):
- supports_edit → one throttled editable progress message for tool activity
- supports_buttons → approval prompts as interactive buttons/cards
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from coffer.application.channel.ports import ChannelAdapter
from coffer.domain.channel.envelopes import SentMessage, encode_approval_value
from coffer.domain.chat.events import (
    ApprovalRequest,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)

_logger = logging.getLogger(__name__)

_EDIT_INTERVAL_SECONDS = 1.5
_TOOL_INPUT_PREVIEW_CHARS = 300
_PROGRESS_MAX_LINES = 8


@dataclass
class PendingApproval:
    conversation_id: str
    chat_id: str
    message_id: str
    tool_name: str


@dataclass
class _Progress:
    lines: dict[str, str] = field(default_factory=dict)  # tool_use_id -> line
    message: SentMessage | None = None
    last_edit: float = 0.0


@dataclass
class TurnRenderer:
    """Renders one turn's events into a chat, for one channel binding."""

    channel: str
    adapter: ChannelAdapter
    chat_id: str
    conversation_id: str
    pending_approvals: dict[str, PendingApproval]
    send: Callable[[str], Awaitable[None]]  # owner-bound safe send

    async def consume(self, queue: asyncio.Queue[Any]) -> None:
        parts: list[str] = []
        progress = _Progress()
        stop_reason = "end_turn"
        error: TurnError | None = None
        while True:
            event = await queue.get()
            if event is None:
                break
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, ToolCall):
                progress.lines[event.tool_use_id] = f"⏳ {event.tool_name}"
                await self._update_progress(progress)
            elif isinstance(event, ToolResult):
                mark = "❌" if event.error else "✅"
                progress.lines[event.tool_use_id] = f"{mark} {event.tool_name}"
                await self._update_progress(progress)
            elif isinstance(event, ApprovalRequest):
                await self._deliver_approval_prompt(event)
            elif isinstance(event, TurnDone):
                stop_reason = event.stop_reason
            elif isinstance(event, TurnError):
                error = event
        await self._finish(parts, stop_reason, error, progress)

    async def _deliver_approval_prompt(self, event: ApprovalRequest) -> None:
        preview = json.dumps(event.tool_input, ensure_ascii=False)
        if len(preview) > _TOOL_INPUT_PREVIEW_CHARS:
            preview = preview[:_TOOL_INPUT_PREVIEW_CHARS] + "…"
        prompt = f"🔐 Approval required: {event.tool_name}\n{preview}"
        try:
            sent = await self.adapter.send_approval_prompt(
                self.chat_id,
                prompt,
                allow_value=encode_approval_value(event.request_id, "allow"),
                deny_value=encode_approval_value(event.request_id, "deny"),
            )
        except Exception:
            _logger.exception("channel.approval.prompt_failed", extra={"channel": self.channel})
            return
        self.pending_approvals[event.request_id] = PendingApproval(
            conversation_id=self.conversation_id,
            chat_id=self.chat_id,
            message_id=sent.message_id,
            tool_name=event.tool_name,
        )

    async def _update_progress(self, progress: _Progress) -> None:
        if not self.adapter.capabilities.supports_edit:
            return
        text = "\n".join(list(progress.lines.values())[-_PROGRESS_MAX_LINES:])
        now = time.monotonic()
        with contextlib.suppress(Exception):
            if progress.message is None:
                progress.message = await self.adapter.send_text(self.chat_id, text)
                progress.last_edit = now
            elif now - progress.last_edit >= _EDIT_INTERVAL_SECONDS:
                await self.adapter.edit_text(self.chat_id, progress.message.message_id, text)
                progress.last_edit = now

    async def _finish(
        self,
        parts: list[str],
        stop_reason: str,
        error: TurnError | None,
        progress: _Progress,
    ) -> None:
        if progress.message is not None:
            with contextlib.suppress(Exception):
                await self.adapter.delete_message(self.chat_id, progress.message.message_id)
        # Prompts left unanswered when the turn ended can no longer be decided.
        for request_id, pending in list(self.pending_approvals.items()):
            del self.pending_approvals[request_id]
            with contextlib.suppress(Exception):
                await self.adapter.resolve_approval_prompt(
                    pending.chat_id, pending.message_id, "⌛ Expired"
                )
        text = "".join(parts).strip()
        if error is not None:
            await self.send(f"⚠️ {error.message} [{error.code}]")
            return
        if stop_reason == "interrupted":
            await self.send(f"{text}\n\n⏹ Stopped." if text else "⏹ Stopped.")
            return
        if not text:
            text = "(the agent returned no text)"
        if stop_reason == "max_iterations":
            text += "\n\n⚠️ Stopped at the tool-iteration limit."
        await self.send(text)
