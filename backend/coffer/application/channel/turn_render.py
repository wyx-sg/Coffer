"""Turn-event rendering for channels: progress and final reply.

Consumes one turn's event queue and turns it into IM traffic, strategy
selected from the adapter's declared capabilities (never its type):
- supports_edit → one throttled editable progress message for tool activity,
  each line describing the call ('⏳ Bash · list the desktop') from its input.

The trailing fact summary compensates for channels that cannot edit and so
show nothing while a turn runs; on an edit-capable channel a clean success
omits it (the live progress + the reply are already the completion signal),
while failures, interrupts, and the tool-iteration limit still send one.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
import re
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
_DESC_MAX_CHARS = 48


def _clip(text: str, limit: int = _DESC_MAX_CHARS) -> str:
    """Collapse whitespace and cap length so a descriptor stays one tidy line."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _basename(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1] if path else ""


def _host(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0]


def _describe_tool(tool_name: str, tool_input: object) -> str:
    """A short human descriptor of what a tool call is doing, drawn from its
    input — so channel progress reads '⏳ Bash · list the desktop' instead of a
    bare '⏳ Bash'. Best-effort and defensive: unknown tools or odd inputs fall
    back to the first string argument, or to nothing."""
    if not isinstance(tool_input, dict):
        return ""

    def field_str(key: str) -> str:
        value = tool_input.get(key)
        return value if isinstance(value, str) else ""

    name = tool_name.lower()
    if name in ("bash", "shell", "exec"):
        return field_str("description") or field_str("command")
    if name in ("read", "write", "edit", "multiedit", "notebookedit"):
        return _basename(field_str("file_path"))
    if name in ("grep", "glob"):
        return field_str("pattern")
    if name == "task":
        return field_str("description")
    if name == "webfetch":
        return _host(field_str("url"))
    if name == "websearch":
        return field_str("query")
    for value in tool_input.values():
        if isinstance(value, str) and value:
            return value
    return ""


def _progress_line(mark: str, tool_name: str, descriptor: str) -> str:
    descriptor = _clip(descriptor)
    return f"{mark} {tool_name} · {descriptor}" if descriptor else f"{mark} {tool_name}"


#: The agent's opt-in to send a file: a markdown image ``![caption](/abs/path)``.
_MEDIA_MARKER = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_MEDIA_MAX_BYTES = 50 * 1024 * 1024  # Telegram sendDocument caps at 50 MB
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


def _is_image_path(path: str) -> bool:
    return pathlib.Path(path).suffix.lower() in _IMAGE_SUFFIXES


def _deliverable(path: str) -> bool:
    """A marker is honoured only for an absolute path to a real, sane-sized file —
    so a relative path or a bare mention in prose never uploads by accident."""
    if not os.path.isabs(path):
        return False
    try:
        p = pathlib.Path(path)
        return bool(p.is_file() and p.stat().st_size <= _MEDIA_MAX_BYTES)
    except OSError:
        return False


@dataclass
class _Progress:
    lines: dict[str, str] = field(default_factory=dict)  # tool_use_id -> line
    desc: dict[str, str] = field(default_factory=dict)  # tool_use_id -> descriptor
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
                descriptor = _describe_tool(event.tool_name, event.tool_input)
                progress.desc[event.tool_use_id] = descriptor
                progress.lines[event.tool_use_id] = _progress_line(
                    "⏳", event.tool_name, descriptor
                )
                await self._update_progress(progress)
            elif isinstance(event, ToolResult):
                mark = "❌" if event.error else "✅"
                # Keep the call's descriptor so the finished line still says what
                # it did ('✅ Read · wedding.json'); the result event omits input.
                progress.lines[event.tool_use_id] = _progress_line(
                    mark, event.tool_name, progress.desc.get(event.tool_use_id, "")
                )
                await self._update_progress(progress)
            elif isinstance(event, TurnDone):
                stop_reason = event.stop_reason
                if event.prompt_tokens is not None or event.completion_tokens is not None:
                    tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
            elif isinstance(event, TurnError):
                error = event
        await self._finish(parts, stop_reason, error, progress)
        # The compact fact summary is the end-of-turn signal on platforms that
        # cannot edit and show nothing mid-turn. On an edit-capable channel the
        # live progress message already served that role, so a clean success
        # sends no trailing summary — the reply itself is the signal. Failures,
        # interrupts, and the tool-iteration limit still send one everywhere.
        clean_success = error is None and stop_reason == "end_turn"
        if not (clean_success and self.adapter.capabilities.supports_edit):
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
        if stop_reason == "max_iterations":
            return f"⚠️ tool-limit · {detail}"
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
        media_sent = 0
        if text and self.adapter.capabilities.supports_media:
            text, media_sent = await self._deliver_media(text)
        if stop_reason == "interrupted":
            body = f"{text}\n\n⏹ Stopped." if text else "⏹ Stopped."
            await self.send(body)
            return
        if not text:
            if media_sent:
                return  # the uploaded file(s) are the reply — no placeholder text
            text = "(the agent returned no text)"
        if stop_reason == "max_iterations":
            text += "\n\n⚠️ Stopped at the tool-iteration limit."
        await self.send(text)

    async def _deliver_media(self, text: str) -> tuple[str, int]:
        """Upload each explicit ``![caption](/abs/path)`` marker whose file exists,
        stripping it from the text. The agent opts in by writing the marker (it is
        told the convention in its channel system prompt); a bare path mentioned in
        prose is not this syntax and never fires, so a misfire needs a deliberate
        marker plus a real on-disk file."""
        sent = 0
        out = text
        for match in _MEDIA_MARKER.finditer(text):
            caption, path = match.group(1).strip(), match.group(2).strip()
            if not _deliverable(path):
                continue
            try:
                await self.adapter.send_media(
                    self.chat_id, path, caption=caption or None, as_photo=_is_image_path(path)
                )
            except Exception:
                continue  # leave the marker in place so the intent is still visible
            sent += 1
            out = out.replace(match.group(0), "", 1).strip()
        return out, sent
