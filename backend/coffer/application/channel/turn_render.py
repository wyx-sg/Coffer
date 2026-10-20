"""Turn-event rendering for channels: the working state, then the reply.

Consumes one turn's event queue and turns it into IM traffic, strategy selected
from the adapter's declared capabilities (never its type):

- supports_live_text → ONE surface the renderer keeps updating for the whole
  turn (see "Show a turn's progress on one live surface").
  Each snapshot is the turn's status block — ``⏳ Working · 2m 14s · 7 steps``,
  the agent's latest narration, the newest step lines (the tool name alone in a
  group; see "Show a turn's working state as one status line") — with the
  answer written so far under it. Telegram's surface is a message it edits or a
  draft; the renderer never knows which. The surface is scaffolding: the
  finished reply is always a new message.
- no live surface (SeaTalk) → nothing but the typing heartbeat while the turn
  runs, then the finished reply.
- The header ticks on the surfaces' keep-alive cadence, so a long silent tool
  still shows time passing.

The finished reply carries only the answer — the text written after the last
tool call — never the narration before it. A clean success sends no trailing
fact summary — the reply is the completion signal. Only a turn that ended
abnormally (failed or interrupted) sends one, carrying its error or stop
signal.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from coffer.application.channel.held_queue import held_buttons
from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.question_flow import QuestionChat, forget_conversation
from coffer.application.channel.reply_rewrite import full_report_button, measure, too_long
from coffer.application.channel.reply_tracking import ReplyTracker
from coffer.application.channel.stop_notice import take as take_stop_notice
from coffer.application.channel.turn_finish import (
    SendCard,
    TurnEnd,
    TurnOutcome,
    deliver_reply,
    held_line,
    stopped_line,
)
from coffer.application.channel.turn_status import LIVE_SEPARATOR, ReplyText, TurnStatus
from coffer.application.channel.turn_surface import TurnSurface, typing_heartbeat
from coffer.application.channel.turn_text import clip_stream_preview, with_mention
from coffer.application.runtime.supervisor import spawn
from coffer.domain.channel.envelopes import ChoiceButton
from coffer.domain.chat.events import (
    MessageEnd,
    QuestionAsked,
    QuestionClosed,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)

#: How long a text-only turn must run before it is worth opening a live surface
#: (always scaffolding — Telegram's): a reply that lands sooner is better served
#: by its own message than by a create-then-delete.
#: NOT a cadence — rate limiting belongs to the transport that knows its limits.
_UPDATE_INTERVAL_SECONDS = 1.5

#: How often the status header is redrawn with a fresh elapsed time. The same
#: cadence as every live surface's own keep-alive (10 s, inside Telegram's 30 s
#: draft preview), so the tick that keeps a surface alive is the tick that moves
#: its clock — no extra traffic.
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
    # The same, for a message with buttons — a question's card (see "Ask the
    # owner in the chat and take the answer back to the agent"); None sends the
    # question as text.
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
    # Cadences, injectable so a test can drive them fast.
    #: What the reply was delivered as, filed for ``/del`` and the 🗑 button; ``None``
    #: (a renderer built without a ledger) tracks nothing.
    tracker: ReplyTracker | None = None
    #: Asked when a cleanly finished reply is too long for a chat, with its line
    #: count: starts the follow-up turn that says it again short and returns
    #: whether it did. The long reply is then not sent (see ``reply_rewrite``).
    #: ``None`` sends every reply as it is — the follow-up turn's own renderer.
    rewrite: Callable[[int], Awaitable[bool]] | None = None
    #: This turn IS that follow-up: its reply carries the full-report button.
    offer_full_report: bool = False
    heartbeat_seconds: float = _TYPING_HEARTBEAT_SECONDS
    tick_seconds: float = _STATUS_TICK_SECONDS
    _status: TurnStatus = field(init=False)
    _reply: ReplyText = field(init=False)
    _surface: TurnSurface = field(init=False)
    #: The moment the status header's clock shows. It moves only with a redraw
    #: (a step, the status tick), never with answer text: text then only APPENDS
    #: to the snapshot on screen, which the surface may write at its fast cadence.
    _clock: float = field(init=False, default=0.0)
    #: The held line and its Continue and Discard, owed after the reply.
    _held_card: tuple[str, list[ChoiceButton]] | None = field(init=False, default=None)

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
        started = self._clock = self.now()
        self._status = TurnStatus(
            started=started, show_steps=self.show_steps, chat_kind=self.chat_kind
        )
        self._reply = ReplyText()
        self._surface = TurnSurface(self.adapter, self.chat_id, self.thread_id, self.chat_kind)
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
                elif isinstance(event, MessageEnd):
                    narration = self._reply.end_message(commentary=event.commentary)
                    if narration.strip():
                        # Text the agent marked as narration: up into the status
                        # block, out of the answer.
                        self._status.narrate(narration)
                        await self._refresh(clock=False)
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
                elif isinstance(event, QuestionAsked):
                    await self._question_asked(event)
                elif isinstance(event, QuestionClosed):
                    await self._questions().closed(event.question)
        finally:
            forget_conversation(self.conversation_id)
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await ticker
        end = TurnEnd(stop_reason, error, len(tool_ids), self.now() - started, tokens)
        answer = self._reply.answer()
        if await self._shortened(answer, end):
            return end.outcome
        if self.offer_full_report and self.tracker is not None:
            self.tracker.extra.append(full_report_button())
        stop_line, stop_noted = await self._rewrite_stop_notice(end)
        await deliver_reply(
            adapter=self.adapter,
            chat_id=self.chat_id,
            thread_id=self.thread_id,
            chat_kind=self.chat_kind,
            surface=self._surface,
            send=self.send,
            mention=self._with_mention,
            text=answer,
            end=end,
            stop_noted=stop_noted,
            stop_line=stop_line,
            tracker=self.tracker,
        )
        await self._send_held_card()
        return end.outcome

    async def _shortened(self, answer: str, end: TurnEnd) -> bool:
        """Hand a reply too long for a chat to the follow-up turn that says it
        short, instead of sending it; ``True`` when that turn took it over. Only
        a clean finish is held back: a failed or stopped turn's partial answer
        goes out with its notice, as it always did."""
        collapses = self.adapter.capabilities.collapses_details
        if (
            self.rewrite is None
            or not end.clean
            or not too_long(answer, collapses_details=collapses)
        ):
            return False
        lines, _ = measure(answer, collapses_details=collapses)
        try:
            taken = await self.rewrite(lines)
        except Exception:
            return False
        if taken:
            # The live surface was this turn's scaffolding; the follow-up opens its own.
            with contextlib.suppress(Exception):
                await self._surface.close("")
        return taken

    def _questions(self) -> QuestionChat:
        return QuestionChat(
            adapter=self.adapter,
            conversation_id=self.conversation_id,
            chat_id=self.chat_id,
            chat_kind=self.chat_kind,
            send=self.send,
            send_card=self.send_card,
        )

    async def _question_asked(self, event: QuestionAsked) -> None:
        """The agent asked the owner and the turn waits: its card goes out."""
        await self._questions().asked(event.question)

    async def _rewrite_stop_notice(self, end: TurnEnd) -> tuple[str | None, bool]:
        """The stopped line a ``/stop`` asked for, and whether it already went
        out by editing the "⏹ Stopping “title”…" message in place. ``(None,
        False)`` when no ``/stop`` stopped this turn.

        Messages the stop held get Continue and Discard (spec channels "Continue
        or discard the messages a stop held"): on the edited line itself, or —
        where the line can only ride the reply as text — on a card of their own
        that follows the reply (``_held_card``)."""
        notice = take_stop_notice(self.conversation_id)
        if notice is None or end.outcome != "stopped":
            return None, False
        buttons = (
            held_buttons(self.conversation_id)
            if notice.held and self.adapter.capabilities.supports_buttons
            else []
        )
        line = stopped_line(
            end.duration,
            title=notice.title,
            tool_count=end.tool_count,
            held=notice.held,
            tappable=bool(buttons),
        )
        if notice.message_id:
            try:
                await self.adapter.update_card(
                    notice.chat_id, notice.message_id, line, buttons, chat_kind=notice.chat_kind
                )
            except Exception:
                pass
            else:
                return line, True
        if buttons and self.send_card is not None:
            self._held_card = (held_line(notice.held, tappable=True), buttons)
            line = stopped_line(end.duration, title=notice.title, tool_count=end.tool_count)
        return line, False

    async def _send_held_card(self) -> None:
        """Continue and Discard under the held line, after the reply."""
        if self._held_card is None or self.send_card is None:
            return
        text, buttons = self._held_card
        self._held_card = None
        with contextlib.suppress(Exception):
            await self.send_card(text, buttons)

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
        now = self._clock
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

    async def _refresh(self, *, clock: bool = True) -> None:
        if clock:
            self._clock = self.now()
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
        await self._refresh(clock=False)

    async def _tick(self) -> None:
        """Redraw the status on a fixed cadence so its clock moves during a long
        silent tool, and open the surface for a turn still thinking in silence."""
        while True:
            await asyncio.sleep(self.tick_seconds)
            with contextlib.suppress(Exception):
                await self._refresh()

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
