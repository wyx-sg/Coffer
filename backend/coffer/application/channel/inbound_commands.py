"""Deciding whether an inbound message is a command, and running it.

Nine words are reserved and nothing else (spec channels "Pass unreserved slash
text to the agent"): a text-only message whose first word names a roster entry
is a command; one whose first word is a near miss of one (``/stpo``) is
answered ``Did you mean /stop?`` and runs nothing; anything else — ``/compact``,
``/Users/me/app crashes``, a removed word like ``/agent`` — is an ordinary
message for the agent and takes the normal turn path. Decided on the message's
OWN text before any thread history is folded in; a caption on a file is always
a message.

Split out of ``inbound`` (that module's size budget) along a real seam: nothing
here queues a turn.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from coffer.application.channel.commands import ChannelCommands
from coffer.application.channel.ephemeral import private_send, safe_send, target_for_command
from coffer.application.channel.inbound_burst import InboundBurst
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import ChannelPeer
from coffer.domain.channel.commands import command_name, near_miss
from coffer.domain.channel.envelopes import InboundMessage

__all__ = ["route_slash"]


async def route_slash(
    *,
    commands: ChannelCommands,
    burst: InboundBurst,
    session: Callable[[str, str, str], Any],
    binding: ChannelBinding,
    peer: ChannelPeer,
    msg: InboundMessage,
    text: str,
    has_attachments: bool,
    conversation_thread_id: str,
) -> bool:
    """Run ``text`` as a command, or correct a near miss; ``True`` when the
    message was consumed and must not become a turn."""
    if has_attachments:
        return False
    name = command_name(text)
    # A command answer is the asker's business, not the room's (see "Keep
    # non-answer chatter private in a group") — a correction all the more.
    send = private_send(safe_send, target_for_command(msg, text))
    if name is None:
        guess = near_miss(text)
        if guess is None:
            return False
        await send(
            binding,
            peer.chat_id,
            f"Did you mean /{guess}?",
            chat_kind=msg.chat_kind,
            thread_id=msg.thread_id,
        )
        return True
    # Whatever this chat/thread holds runs first; `/stop` drops it instead.
    key = (binding.resource.uid, peer.chat_id, msg.thread_id)
    if name == "stop":
        await burst.drop(key)
    else:
        await burst.flush(key)
    # A SeaTalk group's main-chat message roots a new thread; a command there
    # is about the group's defaults (its ``""`` row), while the answer still
    # goes to that thread (spec channels "Set a group's defaults from its main
    # chat"). A non-command there stays an ordinary turn in the new thread.
    group_main = msg.group_main and msg.chat_kind == "group"
    conv_thread = "" if group_main else conversation_thread_id
    await commands.handle(
        binding,
        peer,
        text,
        session(binding.resource.uid, peer.chat_id, conv_thread),
        send,
        chat_kind=msg.chat_kind,
        thread_id=msg.thread_id,
        conversation_thread_id=conv_thread,
        group_main=group_main,
    )
    return True
