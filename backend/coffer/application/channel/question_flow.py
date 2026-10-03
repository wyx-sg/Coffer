"""A question for the owner, in a chat: sending its cards, taking the answer,
rewriting the cards when it closes (spec channels "Ask the owner in the chat and
take the answer back to the agent").

The chat platform raises the question and answers it (``coffer.application.chat
.questions``); this module is the channel's half. It reaches the platform only
through :class:`QuestionPort`, which the composition root satisfies, so the
channel kind never imports the chat kind.

* The turn's renderer hands the turn's ``QuestionAsked`` / ``QuestionClosed``
  events to :class:`QuestionChat`, which sends one card per question (the next
  only after the previous is answered) and rewrites a card in place when its
  question is answered — here, on the Conversations page — or cancelled.
* A card tap (``handle_tap``) answers through the port, ``via`` this channel;
  on a multi-select question it toggles a tick on the card and **Submit**
  answers. The ticks live here, keyed by the question, not on the platform.
* A text message in the chat is the answer while a question is pending
  (``answer_with_text``): it never becomes a turn.

Nothing is ever posted in the owner's name.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from coffer.application.channel.ephemeral import safe_send
from coffer.application.channel.ports import ChannelAdapter, ChannelBinding
from coffer.application.channel.question_card import (
    Tap,
    card_body,
    card_buttons,
    closed_body,
    closed_line,
)
from coffer.application.channel.store_ports import ChannelPeer, ChannelThreadConversationRepoPort
from coffer.application.channel.turn_finish import SendCard
from coffer.domain.channel.envelopes import InboundMessage, SentMessage
from coffer.domain.chat.errors import QuestionAnswerInvalid, QuestionClosed
from coffer.domain.chat.question import QuestionAnswer, QuestionBlock

__all__ = [
    "QuestionChat",
    "QuestionPort",
    "answer_message",
    "answer_with_text",
    "forget_conversation",
    "handle_tap",
]

_logger = logging.getLogger(__name__)


class QuestionPort(Protocol):
    """What the channel needs of the chat platform's questions."""

    def pending_question_for(self, conversation_id: str) -> QuestionBlock | None: ...

    async def answer(
        self,
        conversation_id: str,
        question_id: str,
        *,
        selected: Sequence[str],
        text: str | None,
        via: str,
        by: str,
        index: int | None,
    ) -> QuestionBlock:
        """Answer question ``index`` of ``question_id``; raises
        ``QuestionClosed`` when it was answered, cancelled or gone first and
        ``QuestionAnswerInvalid`` for an answer that does not fit."""
        ...

    async def answer_text(
        self, conversation_id: str, text: str, *, via: str, by: str
    ) -> QuestionBlock | None:
        """Take ``text`` as the answer of the conversation's pending question;
        ``None`` when nothing is pending."""
        ...


@dataclass
class _Cards:
    """The cards of one question, and what a tap needs to know about them."""

    block: QuestionBlock
    conversation_id: str
    chat_id: str
    chat_kind: str
    #: The questions whose card went out, by index; the value is its message id.
    sent: dict[int, str] = field(default_factory=dict)
    #: Cards already rewritten to their closed line.
    rewritten: set[int] = field(default_factory=set)
    #: Ticked options of each multi-select card, by question index.
    ticked: dict[int, set[int]] = field(default_factory=dict)
    #: Questions answered from this chat (the rest were answered in Coffer).
    from_chat: set[int] = field(default_factory=set)


_CARDS: dict[str, _Cards] = {}


def forget_conversation(conversation_id: str) -> None:
    """Drop what is held for a conversation (its turn ended)."""
    for question_id in [q for q, c in _CARDS.items() if c.conversation_id == conversation_id]:
        del _CARDS[question_id]


@dataclass
class QuestionChat:
    """One turn's question cards in one chat."""

    adapter: ChannelAdapter
    conversation_id: str
    chat_id: str
    chat_kind: str
    send: Callable[[str], Awaitable[None]]
    send_card: SendCard | None = None

    async def asked(self, block: QuestionBlock) -> bool:
        """The turn raised ``block`` or one of its questions was answered: show
        the answer where it was given, then the next card. ``True`` for a
        question that is new here."""
        cards = _CARDS.get(block.question_id)
        fresh = cards is None
        if cards is None:
            cards = _CARDS[block.question_id] = _Cards(
                block, self.conversation_id, self.chat_id, self.chat_kind
            )
        cards.block = block
        for index, answer in enumerate(block.answers):
            await self._rewrite(cards, index, closed_line_for(cards, index, block, answer))
        index = block.next_index
        if index < len(block.questions) and index not in cards.sent:
            await self._send_card(cards, index)
        return fresh

    async def closed(self, block: QuestionBlock) -> None:
        """The question left the pending state: every card still open shows how."""
        cards = _CARDS.pop(block.question_id, None)
        if cards is None:
            return
        cards.block = block
        for index in range(len(block.questions)):
            if index < len(block.answers):
                line = closed_line_for(cards, index, block, block.answers[index])
            elif block.status == "cancelled":
                line = closed_line(None, web=False, moment=None)
            else:
                continue
            await self._rewrite(cards, index, line)

    async def _send_card(self, cards: _Cards, index: int) -> None:
        block = cards.block
        buttons = self.send_card is not None and self.adapter.capabilities.supports_buttons
        body = card_body(block, index, buttons=buttons)
        sent: SentMessage | None = None
        try:
            if buttons and self.send_card is not None:
                sent = await self.send_card(body, card_buttons(block, index))
            else:
                await self.send(body)
        except Exception:
            _logger.warning("channel.question.card_failed", exc_info=True)
            return
        cards.sent[index] = sent.message_id if sent is not None else ""

    async def _rewrite(self, cards: _Cards, index: int, line: str) -> None:
        """Rewrite question ``index``'s card to ``line`` in place; where the
        platform cannot (no card update, outside its window, a plain message),
        send the line as a reply."""
        if index in cards.rewritten or index not in cards.sent:
            return
        cards.rewritten.add(index)
        message_id = cards.sent[index]
        if message_id and self.adapter.capabilities.supports_card_update:
            try:
                await self.adapter.update_card(
                    self.chat_id,
                    message_id,
                    closed_body(cards.block, index, line),
                    [],
                    chat_kind=self.chat_kind,
                )
                return
            except Exception:
                _logger.info("channel.question.rewrite_failed", exc_info=True)
        try:
            await self.send(line)
        except Exception:
            _logger.warning("channel.question.line_failed", exc_info=True)


def closed_line_for(cards: _Cards, index: int, block: QuestionBlock, answer: QuestionAnswer) -> str:
    """The line for question ``index``'s card: where it was answered decides the
    wording, and the last answer of a closed block carries the time."""
    last = index == len(block.questions) - 1 and block.status == "answered"
    return closed_line(
        answer,
        web=index not in cards.from_chat,
        moment=block.answered_at if last else None,
    )


async def handle_tap(
    port: QuestionPort,
    tap: Tap,
    *,
    adapter: ChannelAdapter,
    chat_id: str,
    chat_kind: str,
    message_id: str,
    via: str,
    by: str,
) -> None:
    """The owner tapped a question button (already owner-gated by the caller).

    A stale tap — the question closed, its cards gone — changes nothing. A
    single-choice option answers; a multi-select option toggles its tick on the
    card, and **Submit** answers with the ticked options (nothing ticked: nothing
    happens)."""
    cards = _CARDS.get(tap.question_id)
    if cards is None or not 0 <= tap.index < len(cards.block.questions):
        return
    block = cards.block
    if tap.index != block.next_index:
        return
    spec = block.questions[tap.index]
    ticked = cards.ticked.setdefault(tap.index, set())
    if tap.option is None:
        if not spec.multi_select or not ticked:
            return
        selected = [o.label for i, o in enumerate(spec.options) if i in ticked]
    elif not 0 <= tap.option < len(spec.options):
        return
    elif spec.multi_select:
        ticked.symmetric_difference_update({tap.option})
        if adapter.capabilities.supports_card_update:
            try:
                await adapter.update_card(
                    chat_id,
                    cards.sent.get(tap.index) or message_id,
                    card_body(block, tap.index),
                    card_buttons(block, tap.index, ticked),
                    chat_kind=chat_kind,
                )
            except Exception:
                _logger.info("channel.question.toggle_failed", exc_info=True)
        return
    else:
        selected = [spec.options[tap.option].label]
    cards.from_chat.add(tap.index)
    try:
        await port.answer(
            cards.conversation_id,
            tap.question_id,
            selected=selected,
            text=None,
            via=via,
            by=by,
            index=tap.index,
        )
    except (QuestionClosed, QuestionAnswerInvalid):
        cards.from_chat.discard(tap.index)


async def answer_with_text(
    port: QuestionPort,
    conversation_id: str,
    text: str,
    *,
    via: str,
    by: str,
    say: Callable[[str], Awaitable[None]],
) -> bool:
    """Take ``text`` as the answer of the conversation's pending question.
    ``False`` when nothing is pending — the caller then treats the text as an
    ordinary message. An answer that does not fit (too long) is told to the chat
    with ``say`` and still counts as taken."""
    block = port.pending_question_for(conversation_id)
    if block is None:
        return False
    cards = _CARDS.get(block.question_id)
    if cards is not None:
        cards.from_chat.add(block.next_index)
    try:
        return await port.answer_text(conversation_id, text, via=via, by=by) is not None
    except QuestionAnswerInvalid as e:
        await say(f"⚠️ {e}")
        return True
    except QuestionClosed:
        # Answered a moment before: this text is a message like any other.
        return False


async def answer_message(
    port: QuestionPort,
    threads: ChannelThreadConversationRepoPort,
    binding: ChannelBinding,
    peer: ChannelPeer,
    msg: InboundMessage,
    text: str,
    conversation_thread_id: str,
) -> bool:
    """``True`` when the owner's message ``text`` answered the question the
    chat's conversation is waiting on (so it is not a message for the agent)."""
    row = await threads.get(binding.resource.uid, peer.chat_id, conversation_thread_id)
    if row is None or row.active_conversation_id is None:
        return False

    async def say(line: str) -> None:
        await safe_send(
            binding, peer.chat_id, line, thread_id=msg.thread_id, chat_kind=msg.chat_kind
        )

    return await answer_with_text(
        port,
        row.active_conversation_id,
        text,
        via=binding.resource.uid,
        by=msg.sender_display or "owner",
        say=say,
    )
