"""What one command invocation carries, and the two ways it answers.

Every command — typed, or run by tapping a ``cmd:`` button — is about one
conversation thread of one chat and answers into one place, which are not
always the same: a SeaTalk group's main chat answers in the thread its message
rooted but configures the group's defaults row (spec channels "Set a group's
defaults from its main chat"). Bundling those into :class:`CommandContext`
keeps each command module a function of ``(ctx, text)`` instead of a nine-
argument signature repeated across a dozen functions.

``deliver_card`` lives here, beside ``say``, because a card is the other way a
command answers: it reports whether the card landed so the caller can fall back
to the plain-text answer it already has (spec channels "Offer choices and
actions as owner-gated cards": a refused card falls back to the text reply).

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Protocol

from coffer.application.channel.command_text import Settings, settings_in_effect
from coffer.application.channel.ephemeral import is_private
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.selection_cards import SelectionCard
from coffer.application.channel.store_ports import ChannelPeer
from coffer.domain.channel.envelopes import ChoiceButton, EphemeralTarget, SentMessage

if TYPE_CHECKING:
    from coffer.application.channel.commands import ChannelCommands

__all__ = ["CommandContext", "SafeSend", "deliver_card"]

_logger = logging.getLogger(__name__)


class SafeSend(Protocol):
    """Owner-gated send supplied by the processor: ``(binding, chat_id, text)``
    plus optional selection-card ``buttons`` (rendered only where the transport
    ``supports_buttons``; ignored otherwise), the card ``title`` that heads
    them, and the routing pair ``chat_kind``/``thread_id`` (default to a DM
    reply when omitted)."""

    async def __call__(
        self,
        binding: ChannelBinding,
        chat_id: str,
        text: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
        title: str = "",
        chat_kind: str = "direct",
        thread_id: str = "",
        reply_to_message_id: str = "",
        ephemeral: EphemeralTarget | None = None,
    ) -> SentMessage | None: ...


async def deliver_card(
    binding: ChannelBinding,
    peer: ChannelPeer,
    card: SelectionCard,
    *,
    chat_kind: str,
    thread_id: str,
) -> bool:
    """Send ``card``, reporting whether the user actually got it.

    ``False`` means the caller must still answer some other way: the transport
    has no buttons, the card has nothing tappable on it, or the platform refused
    it. Silence is the one outcome a command must never produce, so the refusal
    is logged here and handled there rather than raised.
    """
    if not card.buttons or not binding.adapter.capabilities.supports_buttons:
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
            extra={
                "channel": binding.resource.name,
                "card": card.title,
                "buttons": len(card.buttons),
            },
            exc_info=True,
        )
        return False
    return True


@dataclass(frozen=True)
class CommandContext:
    """One command invocation: who asked, where to answer, what it is about."""

    commands: ChannelCommands
    binding: ChannelBinding
    peer: ChannelPeer
    send: SafeSend
    #: The processor's session for ``conversation_thread_id`` (running turn,
    #: pending document); ``None`` only in unit tests that need neither.
    session: Any
    chat_kind: str
    #: Where the answer goes.
    thread_id: str
    #: Which conversation thread the command is about — ``""`` for a SeaTalk
    #: group's main chat, whose ``""`` row holds the group's defaults.
    conversation_thread_id: str
    #: The command was sent in a SeaTalk group's main chat (see module doc).
    group_main: bool = False
    #: The card a tap came from, rewritten in place where the transport can.
    card_message_id: str = ""
    #: The message the command quotes (``/del`` withdraws that reply), and the
    #: command's own message (which ``/del`` removes where the platform lets it).
    quoted_message_id: str = ""
    command_message_id: str = ""

    @property
    def resource_uid(self) -> str:
        return self.binding.resource.uid

    @property
    def chat_id(self) -> str:
        return self.peer.chat_id

    async def settings(self) -> Settings:
        """What this thread's next turn runs on — for a group's main chat, the
        group's defaults (its ``""`` row, never a conversation)."""
        return await settings_in_effect(
            self.commands,
            self.binding,
            self.peer,
            self.conversation_thread_id,
            chat_kind=self.chat_kind,
            use_conversation=not self.group_main,
        )

    def but(self, **changes: Any) -> CommandContext:
        return replace(self, **changes)

    async def say(self, text: str) -> None:
        await self.send(
            self.binding,
            self.peer.chat_id,
            text,
            chat_kind=self.chat_kind,
            thread_id=self.thread_id,
        )

    async def show(self, card: SelectionCard) -> bool:
        """Put ``card`` in the chat; ``False`` when the caller must answer in text."""
        return await deliver_card(
            self.binding, self.peer, card, chat_kind=self.chat_kind, thread_id=self.thread_id
        )

    async def show_or_say(self, card: SelectionCard, text: str) -> None:
        if not await self.show(card):
            await self.say(text)

    async def answer(self, card: SelectionCard, text: str) -> None:
        """An answer card (status, help) — sent as private text instead where the
        answer is for the asker alone (spec channels "Keep non-answer chatter
        private in a group"): a card is always an ordinary message the whole
        group would see, and these two carry no choice that must be rewritten."""
        if is_private(self.send):
            await self.say(text)
        else:
            await self.show_or_say(card, text)
