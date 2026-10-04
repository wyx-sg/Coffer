"""The person gate for a group message: who may drive a turn from a shared chat
(spec channels "Act in a group only on an addressed message from the owner" and
"Configure when the bot answers in a group").

Split out of ``inbound`` for that module's size budget. Application layer only.
"""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.channel.bot_label import bot_name
from coffer.application.channel.ephemeral import safe_send
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import ChannelPeer, ChannelPeerRepoPort
from coffer.domain.channel.envelopes import InboundMessage

__all__ = ["group_peer"]


async def group_peer(
    peers: ChannelPeerRepoPort, binding: ChannelBinding, msg: InboundMessage
) -> ChannelPeer | None:
    """The group's peer row when ``msg`` may drive a turn, else ``None`` (after
    answering an unpaired sender, the one refusal said aloud)."""
    if binding.require_mention and not msg.addressed:
        # Un-addressed group chatter (no @mention/reply-to-bot) is
        # never a turn — a bot must not speak up uninvited in a group
        # it merely sits in. With ``require_mention`` off the channel
        # lets un-addressed group messages through this gate (still
        # owner-gated by the sender_id checks below).
        return None
    if binding.ignore_other_mentions and msg.mentions_others:
        # "Configure when the bot answers in a group": a group message that
        # @mentions another user is aimed at a human — drop it silently (no
        # reply), before the owner gate, so a bot in a busy group never butts in
        # regardless of who sent it.
        return None
    paired = await peers.sender_ids(binding.resource.uid)
    if not paired:
        # Nobody is paired (no DM/group has a known sender id yet) — a group
        # @mention cannot bootstrap pairing; only the DM/pairing-code flow can.
        return None
    if not msg.sender_id or msg.sender_id not in paired:
        # A group chat is shared, unlike a DM's 1:1 chat_id match — an
        # empty sender_id here (the transport failed to supply one)
        # must never fall through as "assume it's the owner": that
        # would let any member without a resolvable sender_id drive
        # turns on the owner's agent. Refuse whenever ownership can't
        # be proven, not just when it is provably wrong.
        #
        # Aloud only to a member who spoke to the bot. With ``require_mention`` off,
        # un-addressed chatter reaches this line too, and a refusal to every
        # member's every message would make the bot the group's noisiest member.
        if msg.addressed:
            await safe_send(
                binding,
                msg.chat_id,
                f"🚫 Only {bot_name(binding)}\u2019s owners can use it here.",
                thread_id=msg.thread_id,
                chat_kind="group",
            )
        return None
    peer = await peers.get_by_chat(binding.resource.uid, msg.chat_id)
    if peer is None:
        # First @mention from a paired person in this group/thread — record
        # a peer row for it so future turns (and /commands) resolve a
        # conversation scoped to this chat, not the owner's DM.
        peer = ChannelPeer(
            resource_uid=binding.resource.uid,
            chat_id=msg.chat_id,
            display_name=msg.sender_display,
            paired_at=datetime.now(tz=UTC),
            sender_id=msg.sender_id,
        )
        await peers.upsert(peer)
    return peer
