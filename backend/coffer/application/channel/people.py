"""The people a channel answers: its authorised senders, read off its peer rows.

A channel serves every person paired to it with identical rights. Pairing binds a
platform identity (``sender_id``) to the chat it was claimed from; a group the
channel is later addressed in inherits the identity of the paired person who
addressed it ("Treat an addressed group chat as its own peer"). So a person is a
distinct ``sender_id`` across the channel's peer rows, and their rows are their
direct chat plus every group they brought the bot into — removing the person drops
all of them (spec channels "Gate inbound traffic on sender identity").

Application layer only; the rows themselves are persistence's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from coffer.application.channel.store_ports import ChannelPeer

__all__ = ["ChannelPerson", "people_of"]


@dataclass(frozen=True)
class ChannelPerson:
    """One paired person: who they are on the platform and since when."""

    sender_id: str
    display_name: str
    #: When this person was first paired (their earliest peer row).
    paired_at: datetime
    #: Their own direct chat — the earliest-paired row.
    chat_id: str
    #: The conversation their direct chat is driving; filled in by ``status``.
    active_conversation_id: str | None = None


def people_of(peers: list[ChannelPeer]) -> list[ChannelPerson]:
    """The channel's people, earliest paired first. Rows with no sender identity
    belong to nobody (pairing refuses a message that carries none)."""
    first: dict[str, ChannelPeer] = {}
    for peer in sorted(peers, key=lambda p: (p.paired_at, p.chat_id)):
        if peer.sender_id and peer.sender_id not in first:
            first[peer.sender_id] = peer
    return [
        ChannelPerson(
            sender_id=sender_id,
            display_name=peer.display_name,
            paired_at=peer.paired_at,
            chat_id=peer.chat_id,
        )
        for sender_id, peer in first.items()
    ]
