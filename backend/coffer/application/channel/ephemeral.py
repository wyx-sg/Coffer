"""Answers that belong to one member of a group, not to the room (FR-064).

FR-024 stops the bot *acting* on everything said in a group. This is the other
half: stopping it from *saying* everything out loud. ``/status``, ``/help`` and
the selection cards are the asker's own business — announcing each one to
everybody is how a useful bot becomes an unwelcome one.

Where the platform can deliver a message only the asker's client shows
(Telegram ephemeral messages) those answers go that way. The agent's actual
reply never does: that is the conversation the group is having.

Delivery is best-effort by construction — the transport falls back to an
ordinary group message when the platform refuses — so the worst case is the
noise Coffer already made, never a missing answer.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Sequence
from typing import Any

from coffer.application.channel.ports import ChannelBinding
from coffer.domain.channel.commands import is_group_private
from coffer.domain.channel.envelopes import ChoiceButton, EphemeralTarget, InboundMessage

__all__ = ["private_send", "safe_send", "target_for_command"]

_logger = logging.getLogger(__name__)


def target_for_command(msg: InboundMessage, text: str) -> EphemeralTarget | None:
    """The ephemeral target for a command answer, or ``None`` to answer aloud.

    Four things must hold, and each rules out a case where a private answer
    would be wrong or impossible:

    * it is a group — in a DM there is nobody to hide from;
    * the command answers the asker alone (``/new`` and ``/stop`` change shared
      state and stay visible);
    * the platform gave the incoming message an ephemeral id, which is what
      lets any bot answer privately without being a chat administrator;
    * the sender is identified, since an ephemeral message is addressed to a
      user rather than to a chat.
    """
    if msg.chat_kind != "group":
        return None
    command = text.split()[0] if text.split() else ""
    if not is_group_private(command):
        return None
    if not msg.ephemeral_id or not msg.sender_id:
        return None
    return EphemeralTarget(receiver_id=msg.sender_id, ephemeral_message_id=msg.ephemeral_id)


def private_send(send: Any, target: EphemeralTarget | None) -> Any:
    """``send`` with ``ephemeral`` pinned to ``target``.

    Binding it here rather than threading a parameter through every command
    branch keeps the command router unaware that private delivery exists — it
    calls ``send`` and the answer goes wherever this decided.
    """
    if target is None:
        return send
    return functools.partial(send, ephemeral=target)


async def safe_send(
    binding: ChannelBinding,
    chat_id: str,
    text: str,
    *,
    buttons: Sequence[ChoiceButton] | None = None,
    title: str = "",
    thread_id: str = "",
    chat_kind: str = "direct",
    reply_to_message_id: str = "",
    ephemeral: EphemeralTarget | None = None,
) -> None:
    """Send one message through a binding, swallowing a transport failure.

    Every owner-gated reply goes through here — commands, errors, pairing
    confirmations, the turn's own output — which is why it is the place the two
    routing decisions that depend on the chat kind are made:

    * FR-068: only a group needs the reply pointer. In a DM every message is
      plainly an answer, and a reply chain there is just noise.
    * FR-064: ``ephemeral`` is passed through for the transport to honour or
      ignore; it is a request, never a guarantee.

    A failed send is logged, not raised: one undeliverable line must not take
    down the turn that produced it.
    """
    kwargs: dict[str, Any] = {
        "buttons": buttons,
        "title": title,
        "thread_id": thread_id,
        "chat_kind": chat_kind,
        "reply_to_message_id": reply_to_message_id if chat_kind == "group" else "",
        "ephemeral": ephemeral,
    }
    try:
        await binding.adapter.send_text(chat_id, text, **kwargs)
    except Exception:
        _logger.exception("channel.send.failed", extra={"channel": binding.name})
