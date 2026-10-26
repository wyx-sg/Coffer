"""A question for the owner, in a chat: sending its cards, taking the answer,
rewriting the cards when it closes (spec channels
"Ask the owner in the chat and take the chat's answer back to the agent").

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
* In a group a card opens by @mentioning whoever asked, like the reply does,
  and carries the reply's 🗑 (its own ledger entry), which it keeps once closed.
* A question still open when its turn finishes outlives it (spec chat "Keep a
  question open past the turn that asked it"): its cards stay, and once it is
  answered in full the answer is handed back as the text of the owner's next
  message (``late_answer_text``), which starts a turn like any other.

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
    late_answer_text,
)
from coffer.application.channel.reply_tracking import ReplyTracker
from coffer.application.channel.store_ports import ChannelPeer, ChannelThreadConversationRepoPort
from coffer.application.channel.turn_finish import SendCard
from coffer.domain.channel.envelopes import ChoiceButton, InboundMessage, SentMessage
from coffer.domain.chat.errors import QuestionAnswerInvalid, QuestionClosed
from coffer.domain.chat.question import QuestionAnswer, QuestionBlock

__all__ = [
    "QuestionChat",
    "QuestionPort",
    "answer_message",
    "answer_with_text",
    "handle_tap",
    "settle_conversation",
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

    def outlived_turn(self, question_id: str) -> bool:
        """Whether the open question outlived the turn that asked it."""
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
    #: The 🗑 of each card, by question index, kept through every rewrite.
    trash: dict[int, list[ChoiceButton]] = field(default_factory=dict)
    #: Opens a card's text with the asker's @mention; ``None``: no mention.
    mention: Callable[[str], str] | None = None

    #: The turn that asked has finished and the question is still open.
    outlived: bool = False
    #: The sender of these cards, kept for a question that outlives its turn.
    chat: QuestionChat | None = None

    def mentioned(self, body: str) -> str:
        return self.mention(body) if self.mention is not None else body


_CARDS: dict[str, _Cards] = {}


def settle_conversation(conversation_id: str, *, keep: bool) -> None:
    """A turn of the conversation ended: the cards still open outlive it
    (``keep``: it finished on its own) or are dropped (stopped or failed)."""
    for question_id, cards in list(_CARDS.items()):
        if cards.conversation_id != conversation_id or cards.outlived:
            continue
        if keep:
            cards.outlived = True
        else:
            del _CARDS[question_id]


async def _settle_late(cards: _Cards, block: QuestionBlock) -> str:
    """An answer to a question that outlived its turn: no renderer is there to
    show it, so the cards are rewritten (and the next one sent) here. The
    follow-up text once the question is answered in full, else ``""``."""
    if cards.chat is None:
        return ""
    if block.status == "answered":
        await cards.chat.closed(block)
        return late_answer_text(block)
    await cards.chat.asked(block)
    return ""


@dataclass
class QuestionChat:
    """One turn's question cards in one chat."""

    adapter: ChannelAdapter
    conversation_id: str
    chat_id: str
    chat_kind: str
    send: Callable[[str], Awaitable[None]]
    send_card: SendCard | None = None
    #: Opens a card by @mentioning whoever asked, as the reply does (see
    #: ``turn_text.with_mention``).
    mention: Callable[[str], str] | None = None
    #: A fresh ledger entry for one card, so its 🗑 withdraws that card alone;
    #: ``None`` (a renderer built without a ledger) gives cards no 🗑.
    new_tracker: Callable[[], ReplyTracker] | None = None

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
            cards.mention = self.mention
        cards.block = block
        cards.chat = self
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
        body = cards.mentioned(card_body(block, index, buttons=buttons))
        tracker = self.new_tracker() if buttons and self.new_tracker is not None else None
        trash = tracker.buttons() if tracker is not None else []
        sent: SentMessage | None = None
        try:
            if buttons and self.send_card is not None:
                sent = await self.send_card(body, [*card_buttons(block, index), *trash])
            else:
                await self.send(body)
        except Exception:
            _logger.warning("channel.question.card_failed", exc_info=True)
            return
        cards.sent[index] = sent.message_id if sent is not None else ""
        if tracker is not None and trash:
            cards.trash[index] = trash
            tracker.note(sent)
            await tracker.commit()

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
                    cards.mentioned(closed_body(cards.block, index, line)),
                    cards.trash.get(index, []),
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
) -> str:
    """The owner tapped a question button (already owner-gated by the caller).
    Returns the follow-up message an answer to a question that outlived its
    turn becomes, else ``""``.

    A stale tap — the question closed, its cards gone — changes nothing. A
    single-choice option answers; a multi-select option toggles its tick on the
    card, and **Submit** answers with the ticked options (nothing ticked: nothing
    happens)."""
    cards = _CARDS.get(tap.question_id)
    if cards is None or not 0 <= tap.index < len(cards.block.questions):
        return ""
    block = cards.block
    if tap.index != block.next_index:
        return ""
    spec = block.questions[tap.index]
    ticked = cards.ticked.setdefault(tap.index, set())
    if tap.option is None:
        if not spec.multi_select or not ticked:
            return ""
        selected = [o.label for i, o in enumerate(spec.options) if i in ticked]
    elif not 0 <= tap.option < len(spec.options):
        return ""
    elif spec.multi_select:
        ticked.symmetric_difference_update({tap.option})
        if adapter.capabilities.supports_card_update:
            try:
                await adapter.update_card(
                    chat_id,
                    cards.sent.get(tap.index) or message_id,
                    cards.mentioned(card_body(block, tap.index)),
                    [*card_buttons(block, tap.index, ticked), *cards.trash.get(tap.index, [])],
                    chat_kind=chat_kind,
                )
            except Exception:
                _logger.info("channel.question.toggle_failed", exc_info=True)
        return ""
    else:
        selected = [spec.options[tap.option].label]
    cards.from_chat.add(tap.index)
    late = port.outlived_turn(tap.question_id)
    try:
        answered = await port.answer(
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
        return ""
    return await _settle_late(cards, answered) if late else ""


async def answer_with_text(
    port: QuestionPort,
    conversation_id: str,
    text: str,
    *,
    via: str,
    by: str,
    say: Callable[[str], Awaitable[None]],
) -> str | None:
    """Take ``text`` as the answer of the conversation's pending question.
    ``None`` when nothing is pending — the caller then treats the text as an
    ordinary message. Taken, it returns ``""``, or — for the last answer to a
    question that outlived its turn — the follow-up message the caller sends in
    the text's place. An answer that does not fit (too long) is told to the chat
    with ``say`` and still counts as taken."""
    block = port.pending_question_for(conversation_id)
    if block is None:
        return None
    cards = _CARDS.get(block.question_id)
    if cards is not None:
        cards.from_chat.add(block.next_index)
    late = port.outlived_turn(block.question_id)
    try:
        answered = await port.answer_text(conversation_id, text, via=via, by=by)
    except QuestionAnswerInvalid as e:
        await say(f"⚠️ {e}")
        return ""
    except QuestionClosed:
        # Answered a moment before: this text is a message like any other.
        return None
    if answered is None:
        return None
    return await _settle_late(cards, answered) if late and cards is not None else ""


async def answer_message(
    port: QuestionPort,
    threads: ChannelThreadConversationRepoPort,
    binding: ChannelBinding,
    peer: ChannelPeer,
    msg: InboundMessage,
    text: str,
    conversation_thread_id: str,
) -> str | None:
    """Whether the owner's message ``text`` answered the question the chat's
    conversation is waiting on, as ``answer_with_text`` says it."""
    row = await threads.get(binding.resource.uid, peer.chat_id, conversation_thread_id)
    if row is None or row.active_conversation_id is None:
        return None

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
