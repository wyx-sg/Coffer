"""Turn-event rendering for channels: nothing while the turn runs, then the reply.

Consumes one turn's event queue and turns it into IM traffic (spec channels
"Send only the answer, once the turn is done"). While the turn runs the chat
shows only receipt: the reaction on the owner's message and, where the
transport has one, the typing indicator kept alive on a heartbeat. Like a person
replying, the bot then sends one new message.

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
from coffer.application.channel.reply_rewrite import (
    full_report_button,
    measure,
    media_lines,
    too_long,
)
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
from coffer.application.channel.turn_status import ReplyText
from coffer.application.channel.turn_surface import typing_heartbeat
from coffer.application.channel.turn_text import with_mention
from coffer.application.runtime.supervisor import spawn
from coffer.domain.channel.envelopes import ChoiceButton
from coffer.domain.chat.events import (
    MessageEnd,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)

#: Cadence (spec channels "Send only the answer, once the turn is done") for
#: re-sending the typing indicator. SeaTalk shows it for four seconds and Telegram
#: for five; three keeps it continuous, at 20 calls a minute.
_TYPING_HEARTBEAT_SECONDS = 3.0


@dataclass
class TurnRenderer:
    """Renders one turn's events into a chat, for one channel binding."""

    channel: str
    adapter: ChannelAdapter
    chat_id: str
    conversation_id: str
    send: Callable[[str], Awaitable[None]]  # owner-bound safe send
    # The same, for a message with buttons — the card of the messages a stop
    # held; None sends its line as text.
    send_card: SendCard | None = None
    now: Callable[[], float] = time.monotonic  # injectable clock (turn duration)
    # Where in the chat this turn's reply belongs: non-empty ``thread_id``
    # threads the reply; ``chat_kind`` tells a
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
    # The typing cadence, injectable so a test can drive it fast.
    #: What the reply was delivered as, filed for ``/del`` and the 🗑 button; ``None``
    #: (a renderer built without a ledger) tracks nothing.
    tracker: ReplyTracker | None = None
    #: Asked when a cleanly finished reply is too long for a chat, with its line
    #: count: starts the follow-up turn that says it again short and returns
    #: whether it did. The long reply is then not sent (see ``reply_rewrite``).
    #: ``None`` sends every reply as it is — the follow-up turn's own renderer.
    rewrite: Callable[[int, str], Awaitable[bool]] | None = None
    #: This turn IS that follow-up: its reply carries the full-report button.
    offer_full_report: bool = False
    #: The long reply's ``MEDIA:`` lines, which this follow-up's reply sends.
    carried_media: str = ""
    heartbeat_seconds: float = _TYPING_HEARTBEAT_SECONDS
    _reply: ReplyText = field(init=False)
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
        started = self.now()
        self._reply = ReplyText()
        stop_reason = "end_turn"
        error: TurnError | None = None
        tool_ids: set[str] = set()
        tokens: int | None = None
        while True:
            event = await queue.get()
            if event is None:
                break
            if isinstance(event, TextDelta):
                self._reply.add(event.text)
            elif isinstance(event, MessageEnd):
                # Text the agent marked as narration stays out of the answer.
                self._reply.end_message(commentary=event.commentary)
            elif isinstance(event, ToolCall):
                tool_ids.add(event.tool_use_id)
                self._reply.boundary()
            elif isinstance(event, ToolResult):
                self._reply.boundary()
            elif isinstance(event, TurnDone):
                stop_reason = event.stop_reason
                if event.prompt_tokens is not None or event.completion_tokens is not None:
                    tokens = (event.prompt_tokens or 0) + (event.completion_tokens or 0)
            elif isinstance(event, TurnError):
                error = event
        end = TurnEnd(stop_reason, error, len(tool_ids), self.now() - started, tokens)
        answer = self._reply.answer()
        # The long reply's files ride on its short version — once, should the
        # agent have repeated a MEDIA: line itself.
        carried = [m for m in self.carried_media.splitlines() if m and m not in answer]
        if carried:
            answer = "\n\n".join(part for part in (answer, "\n".join(carried)) if part)
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
            taken = await self.rewrite(lines, media_lines(answer))
        except Exception:
            return False
        return taken

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

    def _start_typing_heartbeat(self) -> asyncio.Task[None] | None:
        # A transport with a typing indicator keeps it up while the turn runs, in
        # DMs and group threads alike: the indicator expires within seconds, and
        # it is the only sign of work until the reply lands (see "Send only the
        # answer, once the turn is done").
        caps = self.adapter.capabilities
        if caps.supports_typing:
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
