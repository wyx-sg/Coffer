"""Turn-event rendering for channels: progress and final reply.

Consumes one turn's event queue and turns it into IM traffic, strategy
selected from the adapter's declared capabilities (never its type):
- supports_edit → one throttled editable progress message for tool activity,
  each line describing the call ('⏳ Bash · list the desktop') from its input.

A clean success sends no trailing fact summary on any channel — the reply is
the completion signal. Only a turn that ended abnormally (failed, interrupted,
or at the tool-iteration limit) sends one, carrying its error/stop/limit signal.
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
#: FR-037: cadence for re-sending the typing indicator on a supports_typing-only
#: transport (SeaTalk). Its typing signal expires within seconds, so a long turn
#: needs a periodic re-send to keep the "working…" hint alive.
_TYPING_HEARTBEAT_SECONDS = 8.0


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


def _clip_stream_preview(text: str, limit: int) -> str:
    """FR-037: clip the accumulating reply to the platform's per-message limit for
    an interim streaming edit — editing with the full text could exceed the cap and
    make the edit fail. Keep the TAIL (the most recent words) behind a leading
    ellipsis, so the user watches the answer's latest text grow."""
    if len(text) <= limit:
        return text
    marker = "…"
    return marker + text[-(limit - len(marker)) :]


#: The agent's opt-in to send a file: a line-anchored ``MEDIA:/abs/path``
#: sentinel (Hermes-style), with an optional ``| caption`` after a pipe. Unlike
#: markdown image syntax, this never collides with ordinary prose or a legitimate
#: markdown image the agent wrote only to *reference* a file. The path group
#: allows spaces (absolute macOS paths routinely contain them).
_MEDIA_MARKER = re.compile(
    r"^[ \t]*MEDIA:[ \t]*(?P<path>[^|\n]*?)[ \t]*(?:\|[ \t]*(?P<caption>[^\n]*?))?[ \t]*$",
    re.MULTILINE,
)
_MEDIA_MAX_BYTES = 50 * 1024 * 1024  # Telegram sendDocument caps at 50 MB
_PHOTO_MAX_BYTES = 10 * 1024 * 1024  # sendPhoto caps at 10 MB — larger images go as documents
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
    # FR-037: once reply text starts streaming it takes over the single status
    # message from the tool-progress lines, and a late tool event must not
    # overwrite it back to tool lines.
    text_started: bool = False
    # FR-037: the turn's start time (renderer clock), so a text-only turn can gate
    # opening its streaming status message on ELAPSED TIME — a fast reply opens
    # none (no flicker), a slow/long one does.
    started: float = 0.0


@dataclass
class TurnRenderer:
    """Renders one turn's events into a chat, for one channel binding."""

    channel: str
    adapter: ChannelAdapter
    chat_id: str
    conversation_id: str
    send: Callable[[str], Awaitable[None]]  # owner-bound safe send
    now: Callable[[], float] = time.monotonic  # injectable clock (turn duration)
    # Where in the chat this turn's reply belongs: non-empty ``thread_id``
    # threads the progress message alongside the eventual reply; ``chat_kind``
    # tells a transport whose group/DM send paths differ which one to use.
    thread_id: str = ""
    chat_kind: str = "direct"
    # FR-037: typing-heartbeat cadence (injectable so a test can drive it fast).
    heartbeat_seconds: float = _TYPING_HEARTBEAT_SECONDS

    async def consume(self, queue: asyncio.Queue[Any]) -> bool:
        """Render the turn; return ``True`` on a clean success (no error, a
        normal ``end_turn``), which the driver uses to gate the FR-036 ✅
        completion reaction. An errored/interrupted turn returns ``False``."""
        heartbeat = self._start_typing_heartbeat()
        try:
            return await self._consume(queue)
        finally:
            # Reliably reap the heartbeat so it never outlives the turn.
            if heartbeat is not None:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await heartbeat

    async def _consume(self, queue: asyncio.Queue[Any]) -> bool:
        parts: list[str] = []
        progress = _Progress()
        stop_reason = "end_turn"
        error: TurnError | None = None
        started = self.now()
        progress.started = started
        tool_ids: set[str] = set()
        tokens: int | None = None
        while True:
            event = await queue.get()
            if event is None:
                break
            if isinstance(event, TextDelta):
                parts.append(event.text)
                # FR-037: reply text takes over the single editable status
                # message (a turn runs tools first, then writes its answer).
                progress.text_started = True
                await self._stream_text(progress, parts)
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
        # A clean success sends no trailing fact summary on any channel — the
        # reply itself is the completion signal, and the tool/duration/token
        # facts are just noise. Only a turn that did not end normally (failed,
        # interrupted, or hit the tool-iteration limit) sends a summary, which
        # carries its error / stop / limit signal.
        clean = error is None and stop_reason == "end_turn"
        if not clean:
            await self.send(
                self._summary(error, stop_reason, len(tool_ids), self.now() - started, tokens)
            )
        return clean

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

    def _start_typing_heartbeat(self) -> asyncio.Task[None] | None:
        # FR-037: a supports_typing-but-not-edit transport (SeaTalk) cannot stream
        # — its only non-cluttering keep-alive is the typing indicator (an
        # ephemeral action, zero chat clutter), which expires within seconds, so
        # re-send it on a heartbeat while the turn runs. DM ONLY:
        # single_chat_typing targets a DM and there is no group typing endpoint,
        # so a group/thread turn gets NO interim signal (SeaTalk can neither edit
        # nor delete nor group-type) — the final chunked reply is its completion
        # signal.
        caps = self.adapter.capabilities
        if caps.supports_typing and not caps.supports_edit and self.chat_kind == "direct":
            return asyncio.create_task(self._typing_heartbeat())
        return None

    async def _typing_heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            # Best-effort: a failed heartbeat must never break the turn.
            with contextlib.suppress(Exception):
                await self.adapter.send_typing(self.chat_id)

    async def _update_progress(self, progress: _Progress) -> None:
        # Once reply text is streaming it owns the status message (FR-037) — a
        # late tool event must not overwrite it back to tool lines.
        if progress.text_started:
            return
        text = "\n".join(list(progress.lines.values())[-_PROGRESS_MAX_LINES:])
        await self._render_status(progress, text)

    async def _stream_text(self, progress: _Progress, parts: list[str]) -> None:
        # FR-037: stream the accumulating reply text into the single editable
        # status message (throttled), clipped to the platform limit so a long
        # preview never exceeds the per-message cap and fails the edit. When tool
        # progress already opened the message, morph it into the reply text; on a
        # text-only turn, open the message only once the reply has run past the
        # throttle interval — a fast reply opens NONE (no create → delete → resend
        # flicker; its final send is enough), a slow/long one streams. Interim
        # text is PLAIN (the transport edit is plain, deliberately — partial
        # markdown mid-stream would break the platform's HTML parser); _finish
        # still sends the HTML-rendered, paragraph-chunked, MEDIA-aware final reply.
        if progress.message is None and self.now() - progress.started < _EDIT_INTERVAL_SECONDS:
            return
        text = "".join(parts).strip()
        if not text:
            return
        preview = _clip_stream_preview(text, self.adapter.capabilities.max_message_chars)
        await self._render_status(progress, preview)

    async def _render_status(self, progress: _Progress, text: str) -> None:
        # The one throttled send/edit path both the tool-progress updater and the
        # text-streamer funnel through, so a turn keeps exactly ONE editable
        # status message. Only supports_edit transports get a status message.
        if not self.adapter.capabilities.supports_edit:
            return
        now = self.now()
        with contextlib.suppress(Exception):
            if progress.message is None:
                progress.message = await self.adapter.send_text(
                    self.chat_id, text, thread_id=self.thread_id, chat_kind=self.chat_kind
                )
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
        if text:
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
        """Handle each explicit ``MEDIA:/abs/path`` sentinel line whose file exists.
        The agent opts in by putting a line ``MEDIA:/absolute/path`` (optionally
        ``MEDIA:/absolute/path | caption``) in its reply, told the convention in its
        channel system prompt. Ordinary prose — including a legitimate markdown
        image ``![alt](path)`` the agent wrote only to reference a file — never fires.

        On a media-capable channel the file is uploaded and the sentinel line
        stripped; on a channel without file support the line is replaced with a plain
        note so the user never sees a raw local path for a file that was never
        delivered."""
        supports = self.adapter.capabilities.supports_media
        sent = 0
        out = text
        for match in _MEDIA_MARKER.finditer(text):
            path = (match.group("path") or "").strip()
            caption = (match.group("caption") or "").strip()
            if not _deliverable(path):
                continue  # not a real absolute file — leave the line untouched
            if not supports:
                label = caption or pathlib.Path(path).name
                out = out.replace(
                    match.group(0),
                    f"(couldn't send '{label}' — this channel has no file support)",
                    1,
                ).strip()
                continue
            try:
                # sendPhoto caps at 10 MB; a larger image goes as a document.
                as_photo = (
                    _is_image_path(path) and pathlib.Path(path).stat().st_size <= _PHOTO_MAX_BYTES
                )
                await self.adapter.send_media(
                    self.chat_id,
                    path,
                    caption=caption or None,
                    as_photo=as_photo,
                    thread_id=self.thread_id,
                    chat_kind=self.chat_kind,
                )
            except Exception:
                continue  # leave the line in place so the intent is still visible
            sent += 1
            out = out.replace(match.group(0), "", 1).strip()
        return out, sent
