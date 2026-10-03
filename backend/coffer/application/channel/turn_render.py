"""Turn-event rendering for channels: the working state, then the reply.

Consumes one turn's event queue and turns it into IM traffic, strategy selected
from the adapter's declared capabilities (never its type):

- supports_live_text → ONE surface the renderer keeps updating for the whole
  turn (see "Grow a reply in place on one live surface"). Each snapshot is the
  turn's status block — ``⏳ Working · 2m 14s · 7 steps``, the agent's latest
  narration, the newest step lines (the tool name alone in a group; see "Show a
  turn's working state as one status line") — with the answer written so far
  under it. Telegram's surface is a message it edits or a draft; SeaTalk's is a
  message stream. The renderer never knows which.
- The header ticks on the surfaces' keep-alive cadence, so a long silent tool
  still shows time passing.

A clean success sends no trailing fact summary — the reply is the completion
signal. Only a turn that ended abnormally (failed or interrupted) sends one,
carrying its error or stop signal.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.stop_notice import take as take_stop_notice
from coffer.application.channel.turn_finish import (
    Delivered,
    SendCard,
    TurnEnd,
    TurnOutcome,
    deliver_reply,
    ping_line,
    stopped_line,
)
from coffer.application.channel.turn_status import LIVE_SEPARATOR, ReplyText, TurnStatus
from coffer.application.channel.turn_surface import TurnSurface, typing_heartbeat
from coffer.application.channel.turn_text import clip_stream_preview, with_mention
from coffer.application.runtime.supervisor import spawn
from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult, TurnDone, TurnError

#: How long a text-only turn must run before it is worth opening a live surface
#: on a transport whose surface is scaffolding (Telegram): a reply that lands
#: sooner is better served by its own message than by a create-then-delete.
#: NOT a cadence — rate limiting belongs to the transport that knows its limits.
_UPDATE_INTERVAL_SECONDS = 1.5

#: How often the status header is redrawn with a fresh elapsed time. The same
#: cadence as every live surface's own keep-alive (10 s, inside SeaTalk's 30 s
#: stream timeout and Telegram's 30 s draft preview), so the tick that keeps a
#: surface alive is the tick that moves its clock — no extra traffic.
_STATUS_TICK_SECONDS = 10.0

#: Cadence (spec channels/seatalk "Keep a typing heartbeat alive in DMs and group
#: threads") for re-sending the typing indicator. SeaTalk shows it for four
#: seconds; three keeps it continuous, at 20 calls a minute against 300/min.
_TYPING_HEARTBEAT_SECONDS = 3.0


@dataclass
class TurnRenderer:
    """Renders one turn's events into a chat, for one channel binding."""

    channel: str
    adapter: ChannelAdapter
    chat_id: str
    conversation_id: str
    send: Callable[[str], Awaitable[None]]  # owner-bound safe send
    # The same, for a message with buttons — the question a turn ends on (see
    # "Turn a question for the owner into buttons"); None keeps it as text.
    send_card: SendCard | None = None
    now: Callable[[], float] = time.monotonic  # injectable clock (turn duration)
    # Where in the chat this turn's reply belongs: non-empty ``thread_id``
    # threads the progress alongside the eventual reply; ``chat_kind`` tells a
    # transport whose group/DM send paths differ which one to use.
    thread_id: str = ""
    chat_kind: str = "direct"
    # The id of whoever asked (see "Mention the asker in a group answer"), as the
    # platform addresses them in a mention, and their email as the fallback. Used
    # in a GROUP only, and only where the transport declares the matching
    # template; "" everywhere else.
    mention_user_id: str = ""
    mention_user_email: str = ""
    mention_user_name: str = ""  # for a transport whose mention shows a name
    # The channel's "show steps" setting: off hides the step lines.
    show_steps: bool = True
    # "Ping the asker when a long turn ends": seconds, 0 = never.
    notify_after_seconds: float = 0.0
    # Cadences, injectable so a test can drive them fast.
    heartbeat_seconds: float = _TYPING_HEARTBEAT_SECONDS
    tick_seconds: float = _STATUS_TICK_SECONDS
    _status: TurnStatus = field(init=False)
    _reply: ReplyText = field(init=False)
    _surface: TurnSurface = field(init=False)

    async def consume(self, queue: asyncio.Queue[Any]) -> TurnOutcome:
        """Render the turn; return how it ended (``done`` / ``failed`` /
        ``stopped``), which the driver marks on the asker's message."""
        heartbeat = self._start_typing_heartbeat()
        try:
            return await self._consume(queue)
        finally:
            # Reliably reap the heartbeat so it never outlives the turn.
            if heartbeat is not None:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await heartbeat

    async def _consume(self, queue: asyncio.Queue[Any]) -> TurnOutcome:
        started = self.now()
        self._status = TurnStatus(
            started=started, show_steps=self.show_steps, chat_kind=self.chat_kind
        )
        self._reply = ReplyText()
        self._surface = TurnSurface(
            self.adapter, self.chat_id, self.thread_id, self.chat_kind, self._with_mention
        )
        await self._acknowledge()
        ticker = spawn(self._tick(), name=f"channel-turn-ticker:{self.chat_id}")
        stop_reason = "end_turn"
        error: TurnError | None = None
        tool_ids: set[str] = set()
        tokens: int | None = None
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                if isinstance(event, TextDelta):
                    self._reply.add(event.text)
                    await self._text_update()
                elif isinstance(event, ToolCall):
                    tool_ids.add(event.tool_use_id)
                    self._close_segment()
                    self._status.call(event.tool_use_id, event.tool_name, event.tool_input)
                    await self._refresh()
                elif isinstance(event, ToolResult):
                    self._close_segment()
                    self._status.result(event.tool_use_id, event.tool_name, error=bool(event.error))
                    await self._refresh()
                elif isinstance(event, TurnDone):
                    stop_reason = event.stop_reason
                    if event.prompt_tokens is not None or event.completion_tokens is not None:
                        tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
                elif isinstance(event, TurnError):
                    error = event
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await ticker
        end = TurnEnd(stop_reason, error, len(tool_ids), self.now() - started, tokens)
        stop_noted = await self._rewrite_stop_notice(end)
        delivered = await deliver_reply(
            adapter=self.adapter,
            chat_id=self.chat_id,
            thread_id=self.thread_id,
            chat_kind=self.chat_kind,
            surface=self._surface,
            send=self.send,
            mention=self._with_mention,
            text=self._reply.full(),
            end=end,
            send_card=self.send_card,
            stop_noted=stop_noted,
        )
        if self._ping_due(end, delivered):
            # One new message where the answer's own message was created when
            # the turn began — it replaces the summary of an abnormal ending.
            line = ping_line(end, delivered.body, delivered.question)
            await self.send(self._with_mention(line))
        return "waiting" if delivered.question is not None and end.clean else end.outcome

    async def _rewrite_stop_notice(self, end: TurnEnd) -> bool:
        """Edit the "⏹ Stopping…" a ``/stop`` sent into "⏹ Stopped after 12s."
        where the platform can edit it; ``False`` leaves the result to be said
        in the reply."""
        notice = take_stop_notice(self.conversation_id)
        if notice is None or end.outcome != "stopped":
            return False
        try:
            await self.adapter.update_card(
                notice.chat_id,
                notice.message_id,
                stopped_line(end.duration),
                [],
                chat_kind=notice.chat_kind,
            )
        except Exception:
            return False
        return True

    def _ping_due(self, end: TurnEnd, delivered: Delivered) -> bool:
        """A long turn whose answer finished a message that PERSISTS from the
        turn's start (a SeaTalk stream): finishing it notifies nobody, so the
        end is said once more, in a new message. An answer that went out as a
        new message (Telegram, or a stream that died) already notified, and so
        did a question sent with buttons."""
        return (
            self.notify_after_seconds > 0
            and end.duration >= self.notify_after_seconds
            and self._surface.persisted
            and delivered.in_place
            and not delivered.question_sent
        )

    def _close_segment(self) -> None:
        """A tool event: the text before it was narration — it moves up into
        the status block, and the next text starts a new paragraph."""
        closed = self._reply.boundary()
        if closed.strip():
            self._status.narrate(closed)

    def _snapshot(self) -> str:
        """Status block, then the answer so far under a rule, fitted to the
        platform's per-message cap: the answer's TAIL is kept (the newest words
        are the ones being watched), the step lines go before the header does,
        and only a cap too small for even that clips the whole snapshot."""
        limit = self.adapter.capabilities.max_message_chars
        now = self.now()
        tail = self._reply.tail
        snapshot = ""
        for block in (self._status.block(now), self._status.header(now)):
            if not tail:
                snapshot = block
            else:
                room = limit - len(block) - len(LIVE_SEPARATOR) - 2
                clipped = clip_stream_preview(tail, room) if room > 1 else tail
                snapshot = f"{block}\n{LIVE_SEPARATOR}\n{clipped}"
            if len(snapshot) <= limit:
                return snapshot
        return clip_stream_preview(snapshot, limit)

    async def _refresh(self) -> None:
        await self._surface.show(self._snapshot())

    async def _text_update(self) -> None:
        # On a text-only turn, open a surface only once the reply has run past
        # the update interval — a fast reply opens NONE (no create → delete →
        # resend flicker; its final send is enough), a slow one streams.
        # Interim text is plain; the final reply is rendered once, at the end.
        if not self._surface.is_open and self.now() - self._status.started < (
            _UPDATE_INTERVAL_SECONDS
        ):
            return
        if not self._reply.tail:
            return
        await self._refresh()

    async def _tick(self) -> None:
        """Redraw the status on a fixed cadence so its clock moves during a long
        silent tool, and open the surface for a turn still thinking in silence."""
        while True:
            await asyncio.sleep(self.tick_seconds)
            with contextlib.suppress(Exception):
                await self._refresh()

    async def _acknowledge(self) -> None:
        """Open the live surface immediately, where it PERSISTS as the reply
        (SeaTalk's stream): it opens straight into the status header, so the
        turn is visibly received at no extra cost. A scaffolding surface
        (Telegram's) is opened lazily instead — posting one only to delete it
        would be noise, and the 👀 receipt reaction already says "heard"."""
        caps = self.adapter.capabilities
        if caps.supports_live_text and caps.live_text_persists:
            await self._surface.open(self._status.block(self.now()))

    def _start_typing_heartbeat(self) -> asyncio.Task[None] | None:
        # A transport whose receipt cue is typing (SeaTalk — it cannot react)
        # re-sends it on a heartbeat while the turn runs, in DMs and group
        # threads alike: the indicator expires within seconds. Gated on the
        # receipt mechanism, not on editing (see "Acknowledge receipt and
        # completion by capability").
        caps = self.adapter.capabilities
        if caps.supports_typing and not caps.supports_reactions:
            return spawn(
                typing_heartbeat(
                    self.adapter,
                    self.chat_id,
                    self.thread_id,
                    self.chat_kind,
                    self.heartbeat_seconds,
                ),
                name=f"channel-typing:{self.chat_id}",
            )
        return None

    def _with_mention(self, body: str) -> str:
        """Open the reply by @mentioning whoever asked (see ``turn_text``)."""
        caps = self.adapter.capabilities
        return with_mention(
            body,
            chat_kind=self.chat_kind,
            id_template=caps.mention_template,
            user_id=self.mention_user_id,
            email_template=caps.mention_email_template,
            user_email=self.mention_user_email,
            user_name=self.mention_user_name,
        )
