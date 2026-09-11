"""Turn-event rendering for channels: progress and final reply.

Consumes one turn's event queue and turns it into IM traffic, strategy
selected from the adapter's declared capabilities (never its type):
- supports_live_text → ONE surface the renderer keeps updating for the whole
  turn: tool activity first, each line describing the call ('⏳ Bash · list the
  desktop') from its input, then the reply text taking that same surface over
  as it arrives. Telegram's surface is a message it edits; SeaTalk's is a
  message stream. The renderer never knows which.

A clean success sends no trailing fact summary on any channel — the reply is
the completion signal. Only a turn that ended abnormally (failed, interrupted,
or at the tool-iteration limit) sends one, carrying its error/stop/limit signal.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from coffer.application.channel.ports import ChannelAdapter, LiveText
from coffer.application.channel.turn_media import deliver_media
from coffer.application.channel.turn_progress import _describe_tool, _progress_line
from coffer.domain.chat.events import (
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)

#: How long a turn must run before it is worth opening a live surface at all,
#: on a transport whose surface is scaffolding (Telegram): a reply that lands
#: sooner is better served by its own message than by a create-then-delete.
#:
#: NOT a cadence. The renderer used to throttle every snapshot by this as well,
#: which stacked on top of the surface's own buffer and hid it completely — the
#: reader saw one update every 1.5 s, so a stream opened on its first token and
#: then jumped a paragraph at a time. Rate limiting belongs to the transport
#: that knows its own limits, and each surface now carries its own interval.
_logger = logging.getLogger(__name__)

_UPDATE_INTERVAL_SECONDS = 1.5

#: What a turn says before it has anything to say, on a transport whose live
#: surface becomes the reply. The wait between a message and an answer is the
#: whole of what the user sees otherwise, and on a long turn it reads as the bot
#: having missed the message. This is replaced by the reply itself the moment
#: there is one — the same message, rewritten in place, never a second one.
_ACK_TEXT = "\u23f3 Got it \u2014 working on this\u2026"
_PROGRESS_MAX_LINES = 8
#: FR-037: cadence for re-sending the typing indicator on a supports_typing-only
#: transport (SeaTalk). Its typing signal expires within seconds, so a long turn
#: needs a periodic re-send to keep the "working…" hint alive before the first
#: live update lands.
_TYPING_HEARTBEAT_SECONDS = 8.0


def _clip_stream_preview(text: str, limit: int) -> str:
    """FR-037: clip the accumulating reply to the platform's per-message limit for
    an interim live update — a snapshot longer than the cap would be rejected.
    Keep the TAIL (the most recent words) behind a leading ellipsis, so the user
    watches the answer's latest text grow."""
    if len(text) <= limit:
        return text
    marker = "…"
    return marker + text[-(limit - len(marker)) :]


@dataclass
class _Progress:
    lines: dict[str, str] = field(default_factory=dict)  # tool_use_id -> line
    desc: dict[str, str] = field(default_factory=dict)  # tool_use_id -> descriptor
    # FR-037: the one live surface this turn owns (None until it is opened, and
    # again once it is closed). ``live_tried`` keeps a transport that refuses one
    # from being asked on every event.
    live: LiveText | None = None
    live_tried: bool = False
    # FR-037: once reply text starts streaming it takes over the single live
    # surface from the tool-progress lines, and a late tool event must not
    # overwrite it back to tool lines.
    text_started: bool = False
    # FR-037: the turn's start time (renderer clock), so a text-only turn can gate
    # opening its live surface on ELAPSED TIME — a fast reply opens none (no
    # flicker), a slow/long one does.
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
        await self._acknowledge(progress)
        tool_ids: set[str] = set()
        tokens: int | None = None
        while True:
            event = await queue.get()
            if event is None:
                break
            if isinstance(event, TextDelta):
                parts.append(event.text)
                # FR-037: reply text takes over the single live surface (a turn
                # runs tools first, then writes its answer).
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
        # FR-037: a supports_typing-but-not-edit transport (SeaTalk) has an
        # ephemeral keep-alive nothing else offers — the typing indicator (zero
        # chat clutter), which expires within seconds, so re-send it on a
        # heartbeat while the turn runs. It covers the window BEFORE the live
        # surface opens (a turn that answers instantly opens none at all).
        # Groups get it too: SeaTalk has a group_chat_typing endpoint taking the
        # thread, so the cue appears where the reply will. (This was DM-only on
        # the belief that no such endpoint existed.)
        #
        # Gated on the RECEIPT mechanism, not on editing: a transport that can
        # react (Telegram, 👀 per FR-036) already told the sender it was heard,
        # and one that cannot leans on typing for the same cue. Reading
        # `supports_edit` here happened to give the same answer for both live
        # transports while meaning something else entirely — the exact
        # confusion this capability split exists to remove.
        caps = self.adapter.capabilities
        if caps.supports_typing and not caps.supports_reactions:
            return asyncio.create_task(self._typing_heartbeat())
        return None

    async def _typing_heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            # Best-effort: a failed heartbeat must never break the turn.
            with contextlib.suppress(Exception):
                await self.adapter.send_typing(
                    self.chat_id, thread_id=self.thread_id, chat_kind=self.chat_kind
                )

    async def _update_progress(self, progress: _Progress) -> None:
        # Once reply text is streaming it owns the live surface (FR-037) — a
        # late tool event must not overwrite it back to tool lines.
        if progress.text_started:
            return
        text = "\n".join(list(progress.lines.values())[-_PROGRESS_MAX_LINES:])
        await self._render_status(progress, text)

    async def _stream_text(self, progress: _Progress, parts: list[str]) -> None:
        # FR-037: stream the accumulating reply text into the single live surface
        # (throttled), clipped to the platform limit so a long preview never
        # exceeds the per-message cap. When tool progress already opened the
        # surface, morph it into the reply text; on a text-only turn, open it only
        # once the reply has run past the update interval — a fast reply opens
        # NONE (no create → delete → resend flicker; its final send is enough), a
        # slow/long one streams. Interim text is PLAIN (partial markdown mid-stream
        # would break a platform parser); _finish delivers the rendered,
        # paragraph-chunked, MEDIA-aware final reply.
        if progress.live is None and self.now() - progress.started < _UPDATE_INTERVAL_SECONDS:
            return
        text = "".join(parts).strip()
        if not text:
            return
        preview = _clip_stream_preview(text, self.adapter.capabilities.max_message_chars)
        await self._render_status(progress, preview)

    async def _render_status(self, progress: _Progress, text: str) -> None:
        # The one throttled path both the tool-progress updater and the text
        # streamer funnel through, so a turn keeps exactly ONE live surface.
        # A transport that has none (or refuses to open one) simply gets no
        # interim traffic — its final reply is the whole signal.
        if progress.live is None:
            await self._open_live(progress, text)
            return
        # No throttle here: ``update`` is a no-op inside the surface's own
        # interval and when the snapshot has not changed, so offering every
        # snapshot lets the transport render at the cadence it can sustain.
        with contextlib.suppress(Exception):
            await progress.live.update(text)

    async def _acknowledge(self, progress: _Progress) -> None:
        """Open the live surface immediately, so the turn is visibly received.

        Only where that surface PERSISTS. SeaTalk's stream opens by posting a
        real message and grows it in place, so the acknowledgement costs nothing
        extra — it becomes the reply. Telegram's live surface is scaffolding the
        renderer deletes before sending the real answer, so opening it up front
        would post something only to take it away again; there the ordinary lazy
        open still applies, and the 👀 receipt reaction already says "heard".
        """
        caps = self.adapter.capabilities
        if not (caps.supports_live_text and caps.live_text_persists):
            return
        await self._open_live(progress, _ACK_TEXT)

    async def _open_live(self, progress: _Progress, text: str) -> None:
        if progress.live_tried or not self.adapter.capabilities.supports_live_text:
            return
        progress.live_tried = True  # ask once per turn, whatever the answer
        try:
            progress.live = await self.adapter.open_live_text(
                self.chat_id, thread_id=self.thread_id, chat_kind=self.chat_kind
            )
        except Exception:
            # Swallowed so a transport that cannot stream still answers, but
            # logged: the degraded result — a reply delivered in one piece —
            # looks exactly like a turn that never tried to stream, and
            # without this the difference cannot be seen from outside.
            _logger.warning("channel.live_text.open_failed", exc_info=True)
            return
        if progress.live is None:
            return
        with contextlib.suppress(Exception):
            await progress.live.update(text)

    async def _finish(
        self,
        parts: list[str],
        stop_reason: str,
        error: TurnError | None,
        progress: _Progress,
    ) -> None:
        text = "".join(parts).strip()
        if error is not None:
            await self._deliver(progress, f"⚠️ {error.message} [{error.code}]")
            return
        media_sent = 0
        if text:
            text, media_sent = await deliver_media(
                self.adapter,
                self.chat_id,
                text,
                thread_id=self.thread_id,
                chat_kind=self.chat_kind,
            )
        if stop_reason == "interrupted":
            await self._deliver(progress, f"{text}\n\n⏹ Stopped." if text else "⏹ Stopped.")
            return
        if not text:
            if media_sent:
                # The uploaded file(s) are the reply — no placeholder text, but
                # the live surface still has to be closed.
                await self._close_live(progress, "")
                return
            text = "(the agent returned no text)"
        if stop_reason == "max_iterations":
            text += "\n\n⚠️ Stopped at the tool-iteration limit."
        await self._deliver(progress, text)

    async def _deliver(self, progress: _Progress, body: str) -> None:
        """Close the live surface with the final ``body`` and send whatever it
        could not deliver itself. A surface that finishes the reply in place
        (SeaTalk's stream IS the message) leaves nothing to send; one that is
        only scaffolding (Telegram's status message) hands it all back."""
        leftover = await self._close_live(progress, body)
        if leftover:
            await self.send(leftover)

    async def _close_live(self, progress: _Progress, body: str) -> str:
        live, progress.live = progress.live, None
        if live is None:
            return body
        try:
            return await live.close(body)
        except Exception:
            # A surface that failed to close is spent, never retried — the
            # ordinary send path still owes the user the reply.
            return body
