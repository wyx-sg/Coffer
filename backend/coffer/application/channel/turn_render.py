"""Turn-event rendering for channels: progress and final reply.

Consumes one turn's event queue and turns it into IM traffic, strategy
selected from the adapter's declared capabilities (never its type):
- supports_edit → one throttled editable progress message for tool activity
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from coffer.application.channel.ports import ChannelAdapter
from coffer.domain.channel.envelopes import SentMessage
from coffer.domain.chat.events import (
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)

_EDIT_INTERVAL_SECONDS = 1.5
_PROGRESS_MAX_LINES = 8


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
    send: Callable[[str], Awaitable[None]]  # owner-bound safe send
    now: Callable[[], float] = time.monotonic  # injectable clock (turn duration)

    async def consume(self, queue: asyncio.Queue[Any]) -> None:
        parts: list[str] = []
        progress = _Progress()
        stop_reason = "end_turn"
        error: TurnError | None = None
        started = self.now()
        tool_ids: set[str] = set()
        tokens: int | None = None
        while True:
            event = await queue.get()
            if event is None:
                break
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, ToolCall):
                tool_ids.add(event.tool_use_id)
                progress.lines[event.tool_use_id] = f"⏳ {event.tool_name}"
                await self._update_progress(progress)
            elif isinstance(event, ToolResult):
                mark = "❌" if event.error else "✅"
                progress.lines[event.tool_use_id] = f"{mark} {event.tool_name}"
                await self._update_progress(progress)
            elif isinstance(event, TurnDone):
                stop_reason = event.stop_reason
                if event.prompt_tokens is not None or event.completion_tokens is not None:
                    tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
            elif isinstance(event, TurnError):
                error = event
        await self._finish(parts, stop_reason, error, progress)
        # Every turn ends with a compact fact summary — the only end-of-turn
        # signal on platforms that cannot edit and show nothing mid-turn.
        await self.send(
            self._summary(error, stop_reason, len(tool_ids), self.now() - started, tokens)
        )

    @staticmethod
    def _summary(
        error: TurnError | None,
        stop_reason: str,
        tool_count: int,
        duration: float,
        tokens: int | None,
    ) -> str:
        facts = [f"{tool_count} tool" + ("" if tool_count == 1 else "s"), f"{duration:.1f}s"]
        if tokens is not None:
            facts.append(f"{tokens} tok")
        detail = " · ".join(facts)
        if error is not None:
            return f"⚠️ failed · {detail}"
        if stop_reason == "interrupted":
            return f"⏹ stopped · {detail}"
        return f"✅ done · {detail}"

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
