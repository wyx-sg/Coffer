"""A selection card's life in the chat: put it there, then keep it honest.

A "helper module beside ``commands.py``" like ``content_ops.py`` is to the skill
service: free functions doing the card's I/O against the binding's adapter, kept
out of that file so it stays inside the component size cap.

Why the rewrite half exists: before it, tapping a card switched the agent (or
model) and posted a confirmation, but left the card itself untouched — still
showing the old choice ticked and still offering the option the user had just
taken. Tapping it again was a no-op the card actively invited. SeaTalk's Update
Message and Telegram's ``editMessageText`` both let the card be rewritten in
place, so it is.

Why the delivery half exists: a card is a richer payload than text and a
platform can refuse it outright — SeaTalk answered ``code=102`` to a ``/model``
card built from a 29-model catalogue. The refusal used to end the command in
silence. ``deliver_card`` reports whether the card landed so the caller can fall
back to the plain-text answer it already has.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.application.channel.conversation_ops import ensure_conversation
from coffer.application.channel.ports import ChannelBinding, ChannelPeer
from coffer.application.channel.selection_cards import SelectionCard, agent_card, model_card

if TYPE_CHECKING:
    from coffer.application.channel.commands import ChannelCommands

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


async def _current_card(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    kind: str,
    thread_id: str,
) -> SelectionCard | None:
    """Re-read what is now in effect and render that card.

    Deliberately re-reads rather than assuming the tapped value took: the switch
    is what the card must reflect, and only the store knows whether it landed.
    """
    row = await commands._threads.get(binding.resource_id, peer.chat_id, thread_id)
    agent_key = (row.preferred_agent if row is not None else None) or binding.default_agent
    if kind == "agent":
        return agent_card(current=agent_key, choices=commands._agents.agent_choices())
    if kind != "model":
        return None
    conversation_id = await ensure_conversation(
        commands._conversations, commands._threads, binding, peer, thread_id
    )
    cfg = await commands._conversations.get_agent_config(conversation_id)
    return model_card(current=cfg.model, picks=await commands._model_suggestions.suggest(agent_key))
