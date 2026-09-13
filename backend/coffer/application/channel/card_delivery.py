"""A selection card's life in the chat: put it there, route a tap, keep it honest.

A "helper module beside ``commands.py``" like ``content_ops.py`` is to the skill
service: free functions doing the card's I/O against the binding's adapter, kept
out of that file so it stays inside the component size cap.

Why the delivery half exists: a card is a richer payload than text and a
platform can refuse it outright — SeaTalk answered ``code=102`` to a ``/model``
card built from a 29-model catalogue. The refusal used to end the command in
silence. ``deliver_card`` reports whether the card landed so the caller can fall
back to the plain-text answer it already has.

Why the rewrite half exists: before it, tapping a card switched the agent (or
model) and posted a confirmation, but left the card itself untouched — still
showing the old choice ticked and still offering the option the user had just
taken. Tapping it again was a no-op the card actively invited. SeaTalk's Update
Message and Telegram's ``editMessageText`` both let the card be rewritten in
place, so it is.

Why the page half exists: the same rewrite turns a bounded card into a browsable
one. A Prev/Next tap re-renders the SAME message at another window of the same
list — the one thing it must never do is change what is in effect, so it is
routed apart from a choice before any switch code is reached.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.application.channel.conversation_ops import ensure_conversation
from coffer.application.channel.ports import ChannelBinding, ChannelPeer
from coffer.application.channel.selection_cards import (
    SelectionCard,
    agent_card,
    is_page_turn,
    model_card,
    parse_page_turn,
)

if TYPE_CHECKING:
    from coffer.application.channel.commands import ChannelCommands, SafeSend

_logger = logging.getLogger(__name__)


async def deliver_card(
    binding: ChannelBinding,
    peer: ChannelPeer,
    card: SelectionCard,
    *,
    chat_kind: str,
    thread_id: str,
) -> bool:
    """Send ``card``, reporting whether the user actually got it.

    ``False`` means the caller must still answer some other way: either the card
    has nothing tappable on it, or the platform refused it. Silence is the one
    outcome a command must never produce, so the refusal is logged here and
    handled there rather than raised.
    """
    if not card.buttons:
        return False
    try:
        await binding.adapter.send_text(
            peer.chat_id,
            card.text,
            buttons=card.buttons,
            title=card.title,
            thread_id=thread_id,
            chat_kind=chat_kind,
        )
    except Exception:
        _logger.warning(
            "channel.card.rejected",
            extra={"channel": binding.name, "card": card.title, "buttons": len(card.buttons)},
            exc_info=True,
        )
        return False
    return True


async def dispatch_card_tap(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    data: str,
    send: SafeSend,
    *,
    chat_kind: str,
    thread_id: str,
    card_message_id: str,
) -> None:
    """Route one owner-gated tap: a page turn, or a choice.

    The page question is asked FIRST and answered exhaustively. A navigation
    value never reaches ``apply_agent``/``apply_model``, and a value that merely
    looks like navigation (``page:`` with a kind or index we do not render) is
    dropped rather than falling through to the code path that applies a choice.
    """
    turn = parse_page_turn(data)
    if turn is not None:
        kind, page = turn
        await turn_card_page(
            commands,
            binding,
            peer,
            kind,
            page,
            send,
            chat_kind=chat_kind,
            thread_id=thread_id,
            card_message_id=card_message_id,
        )
        return
    kind, _, value = data.partition(":")
    if kind == "agent":
        if value not in commands._agents.agent_keys():
            await send(
                binding,
                peer.chat_id,
                f"Unknown agent '{value}'.",
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        await commands.apply_agent(
            binding, peer, value, send, chat_kind=chat_kind, thread_id=thread_id
        )
    elif kind == "model" and value:
        await commands.apply_model(
            binding, peer, value, send, chat_kind=chat_kind, thread_id=thread_id
        )
    else:
        return
    await refresh_selection_card(
        commands, binding, peer, card_message_id, kind, chat_kind=chat_kind, thread_id=thread_id
    )


async def refresh_selection_card(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    card_message_id: str,
    kind: str,
    *,
    chat_kind: str,
    thread_id: str,
) -> None:
    """Rewrite the tapped card so its tick sits on the new choice.

    The card is rebuilt with no page given, which lands it on the page holding
    the choice now in effect — the page the tap came from. A choice therefore
    leaves the user exactly where they were, with the tick moved.

    Best-effort by design. The switch already happened and was confirmed in
    chat, so a transport that cannot update a card — or an update that fails
    because the card aged past SeaTalk's 7-day window, or the platform
    rate-limited us — must not turn a successful switch into a visible error.
    It is logged and dropped.
    """
    caps = binding.adapter.capabilities
    if not (card_message_id and caps.supports_buttons and caps.supports_card_update):
        return
    try:
        card = await _current_card(commands, binding, peer, kind, thread_id)
        if card is None or not card.buttons:
            return
        await binding.adapter.update_card(
            peer.chat_id,
            card_message_id,
            card.text,
            card.buttons,
            title=card.title,
            chat_kind=chat_kind,
        )
    except Exception:
        _logger.warning(
            "channel.card.refresh_failed", extra={"channel": binding.name}, exc_info=True
        )


async def turn_card_page(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    kind: str,
    page: int,
    send: SafeSend,
    *,
    chat_kind: str,
    thread_id: str,
    card_message_id: str,
) -> None:
    """Show another page of the same card, changing nothing else.

    The card is rebuilt from what is CURRENTLY in effect, exactly as a refresh
    is — a page turn reads state and never writes it, so the tick stays where
    the last actual choice put it.

    Unlike a refresh, a page turn is not cosmetic: the user asked to see
    something and must see it. So the failures degrade rather than drop.

    * The card cannot be rewritten in place (no message id, a transport without
      ``supports_card_update``, an update the platform refused because the card
      aged past SeaTalk's 7-day window or we were rate-limited) → the page is
      posted as a FRESH card. The old card stays in the chat showing an older
      page, which is harmless: a card's page is a view, not a claim about state.
    * That fresh card is refused too → the page goes out as plain text.
    """
    try:
        card = await _current_card(commands, binding, peer, kind, thread_id, page=page)
    except Exception:
        _logger.warning("channel.card.page_failed", extra={"channel": binding.name}, exc_info=True)
        card = None
    if card is None or not card.buttons:
        await send(
            binding,
            peer.chat_id,
            f"Could not turn the page — send /{kind} for a fresh card.",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    caps = binding.adapter.capabilities
    if card_message_id and caps.supports_card_update:
        try:
            await binding.adapter.update_card(
                peer.chat_id,
                card_message_id,
                card.text,
                card.buttons,
                title=card.title,
                chat_kind=chat_kind,
            )
            return
        except Exception:
            _logger.warning(
                "channel.card.page_update_failed",
                extra={"channel": binding.name, "card": card.title, "page": card.page},
                exc_info=True,
            )
    if await deliver_card(binding, peer, card, chat_kind=chat_kind, thread_id=thread_id):
        return
    await send(binding, peer.chat_id, card_as_text(card), chat_kind=chat_kind, thread_id=thread_id)


def card_as_text(card: SelectionCard) -> str:
    """The card written out for a transport that will not take it as a card.

    Navigation is dropped — there is nothing to tap on a text message — so the
    page's own choices are what survives, under the same body that names what
    is currently in effect.
    """
    choices = [b.label for b in card.buttons if not is_page_turn(b.value)]
    return "\n".join([card.title, card.text, *(f"• {label}" for label in choices)])


async def _current_card(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    kind: str,
    thread_id: str,
    *,
    page: int | None = None,
) -> SelectionCard | None:
    """Re-read what is now in effect and render that card.

    Deliberately re-reads rather than assuming the tapped value took: the switch
    is what the card must reflect, and only the store knows whether it landed.
    ``page`` is ``None`` for "the page holding the current choice".
    """
    row = await commands._threads.get(binding.resource_id, peer.chat_id, thread_id)
    agent_key = (row.preferred_agent if row is not None else None) or binding.default_agent
    if kind == "agent":
        return agent_card(current=agent_key, choices=commands._agents.agent_choices(), page=page)
    if kind != "model":
        return None
    conversation_id = await ensure_conversation(
        commands._conversations, commands._threads, binding, peer, thread_id
    )
    cfg = await commands._conversations.get_agent_config(conversation_id)
    picks = await commands._model_suggestions.suggest(agent_key)
    return model_card(current=cfg.model, picks=picks, page=page)
