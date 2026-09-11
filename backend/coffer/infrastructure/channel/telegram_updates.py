"""Non-message Telegram updates.

The poll loop subscribes to exactly the updates that change Coffer's own
state. Today that is one: the bot's own membership of a chat
(``my_chat_member``) — added to a group, removed from it, or blocked in a DM.
Everything else the platform can push (reactions to the bot's messages, chat
boosts, join requests, poll answers) has no consequence here and is left
unsubscribed: an update Coffer does nothing with is cost without benefit.

Pure parsing, split out of ``telegram.py`` to keep that file inside the size
cap. The adapter owns the callback; this module owns what the payload means.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.channel.envelopes import InboundCallback, InboundLifecycle, InboundStop
from coffer.infrastructure.channel.telegram_parse import is_group

__all__ = [
    "ALLOWED_UPDATES",
    "callback_from_query",
    "lifecycle_from_update",
    "stop_from_update",
    "tap_ack",
]

#: Exactly what ``getUpdates`` is asked for. Telegram withholds
#: ``my_chat_member`` unless it is named here — the default set omits it.
ALLOWED_UPDATES: tuple[str, ...] = (
    "message",
    "callback_query",
    "my_chat_member",
    # FR-063: the user pressed the stop control on a streamed draft. An older
    # Bot API server simply never sends this one; naming it costs nothing.
    "stopped_message_generation",
)

#: ChatMember statuses that mean the bot is still in the chat. "restricted" is
#: deliberately absent from this set: a restricted member may or may not still
#: be in the chat, which its own ``is_member`` field settles below.
_PRESENT = frozenset({"creator", "administrator", "member"})
#: …and the ones that mean it is not. Listed rather than inferred so a status
#: Telegram adds later is treated as "unknown", not silently as "gone" — the
#: destructive reading must never be the default.
_ABSENT = frozenset({"left", "kicked"})


def lifecycle_from_update(
    update: dict[str, Any], *, channel: str, bot_id: int | None
) -> InboundLifecycle | None:
    """Read a ``my_chat_member`` update as a lifecycle event, or ``None``.

    Telegram reports the bot's own membership where SeaTalk reports a removal
    event; both mean the same thing to Coffer, so both land on the one
    ``InboundLifecycle`` (FR-058) rather than growing a second envelope per
    platform. Only a DEPARTURE is an event — being added changes nothing until
    somebody pairs (FR-005), and that is a message, not this.

    ``None`` covers a malformed payload, an update about somebody other than
    this bot, an arrival, and a status transition whose meaning is not known —
    in every one of those cases doing nothing is correct, and dropping a peer
    binding is not.
    """
    changed = update.get("my_chat_member")
    if not isinstance(changed, dict):
        return None
    chat = changed.get("chat")
    new_member = changed.get("new_chat_member")
    if not isinstance(chat, dict) or not isinstance(new_member, dict):
        return None
    user = new_member.get("user")
    if bot_id is not None and isinstance(user, dict) and user.get("id") != bot_id:
        # ``my_chat_member`` is only ever about the bot, but the guard costs
        # nothing and a mis-routed update must not unbind somebody's channel.
        return None
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return None
    if _is_present(new_member) is not False:
        return None
    return InboundLifecycle(channel=channel, chat_id=chat_id, kind="removed_from_group")


def _is_present(new_member: dict[str, Any]) -> bool | None:
    """Whether the status leaves the bot in the chat; ``None`` when unknown."""
    status = str(new_member.get("status") or "")
    if status in _PRESENT:
        return True
    if status in _ABSENT:
        return False
    if status == "restricted":
        # A restricted member is still in the chat unless is_member says not.
        return bool(new_member.get("is_member", True))
    return None


def callback_from_query(query: dict[str, Any], *, channel: str) -> InboundCallback:
    """Normalise a ``callback_query`` (a selection-card tap).

    A card tapped in a (super)group replies back into that group/thread, not a
    DM, so the routing comes from the CARD's own message rather than from the
    tapper (FR-034).
    """
    sender = query.get("from") or {}
    card = query.get("message") or {}
    return InboundCallback(
        channel=channel,
        chat_id=str(card.get("chat", {}).get("id", "")),
        sender_id=str(sender.get("id") or ""),
        data=str(query.get("data") or ""),
        callback_id=str(query.get("id") or ""),
        platform_message_id=str(card.get("message_id", "")),
        chat_kind="group" if is_group(card) else "direct",
        thread_id=str(card.get("message_thread_id") or ""),
    )


def tap_ack(data: str) -> str:
    """The bubble shown the instant a card button is tapped. ``data`` is an
    opaque ``kind:value`` payload (``agent:claude_code``); show the value,
    which is what the user chose, and fall back to a bare acknowledgement."""
    _, _, value = data.partition(":")
    return f"\u2713 {value}" if value else "\u2713"


def stop_from_update(update: dict[str, Any], *, channel: str) -> InboundStop | None:
    """Read a ``stopped_message_generation`` update (FR-063), or ``None``.

    The draft id is deliberately not carried through: Coffer keys a turn by
    ``(channel, chat, thread)``, which is exactly what the update names, and the
    only turn a stop could mean is the one running there.
    """
    stopped = update.get("stopped_message_generation")
    if not isinstance(stopped, dict):
        return None
    chat = stopped.get("chat")
    if not isinstance(chat, dict):
        return None
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return None
    thread = stopped.get("message_thread_id")
    return InboundStop(
        channel=channel,
        chat_id=chat_id,
        thread_id=str(thread) if thread else "",
        # A DM can carry topics too, so the thread id does not say which this
        # is — the chat's own type does.
        chat_kind="group" if is_group(stopped) else "direct",
    )
