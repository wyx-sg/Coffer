"""One inbound message, ready to become a turn — and what a tool called from
that turn may learn about it.

Split out of ``turn_driver`` (its size budget); ``turn_driver`` re-exports
:class:`QueuedInbound` so every importer keeps one import.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.channel.scheduled_turn import ScheduledTurn
from coffer.application.channel.turn_origin import TurnOrigin
from coffer.domain.chat.attachment import Attachment

__all__ = ["QueuedInbound", "origin_of_turn"]


@dataclass(frozen=True)
class QueuedInbound:
    """One inbound message, ready to become a turn.

    ``text`` drives the turn (it opens with the origin block of "Open every turn with
    its message origin"); ``attachments`` are the downloaded files to materialise for
    the agent; ``thread_id`` / ``chat_kind`` route the reply back to where the message
    came from; ``reply_to_message_id`` is the user's inbound platform_message_id the
    receipt/completion reactions target (see "Acknowledge receipt and completion by
    capability"; "" when the transport supplied none); the mention id and address are
    what a group reply opens by @mentioning (see "Mention the asker in a group answer"),
    with the display name a platform that spells mentions by name needs;
    and ``title_hint`` is the human's own words, carried apart from the driving text
    (spec chat "Keep the conversation index without its text"; "" when nothing was
    nameable). ``conversation_thread_id`` is which of the chat's conversations the
    turn joins — ``thread_id`` itself, or ``""`` for a casual direct-chat
    reply-in-thread that belongs to the direct chat's conversation (see "Key
    conversation identity by channel, chat and thread").
    """

    text: str
    attachments: tuple[Attachment, ...] = ()
    thread_id: str = ""
    chat_kind: str = "direct"
    reply_to_message_id: str = ""
    mention_user_id: str = ""
    mention_user_email: str = ""
    mention_user_name: str = ""
    title_hint: str = ""
    conversation_thread_id: str = ""
    #: The inbound message ids of the earlier messages a burst folded into this
    #: turn (``reply_to_message_id`` is the last one's). Each of them carries the
    #: turn's progress marks, so none is left on its receipt mark.
    earlier_message_ids: tuple[str, ...] = ()
    #: Coffer's follow-up asking for a too-long reply again, short (``reply_rewrite``).
    rewrite: bool = False
    #: Whether the person who sent it owns the bot (a group's others may only ask).
    asker_is_owner: bool = True
    #: Set when a scheduled task started the turn rather than a message.
    scheduled: ScheduledTurn | None = None


def origin_of_turn(channel_uid: str, chat_id: str, item: QueuedInbound) -> TurnOrigin:
    """What a tool the agent calls from this turn may ask about it."""
    scheduled = item.scheduled
    return TurnOrigin(
        channel_uid=channel_uid,
        chat_id=chat_id,
        chat_kind=item.chat_kind,
        thread_id=item.thread_id,
        conversation_thread_id=item.conversation_thread_id,
        asker_is_owner=item.asker_is_owner,
        mention_user_id=item.mention_user_id,
        mention_user_email=item.mention_user_email,
        mention_user_name=item.mention_user_name,
        task_uid=scheduled.task_uid if scheduled else "",
        task_repeats=scheduled.repeats if scheduled else False,
        chain_started_at=scheduled.chain_started_at if scheduled else None,
        chain_index=scheduled.chain_index if scheduled else 0,
    )
