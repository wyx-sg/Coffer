"""The inbound callbacks that are NOT a message: card taps and lifecycle events.

Split out of ``InboundProcessor`` for the same reason ``turn_driver`` was (that
module sits at the file-size limit), and along a real seam: neither path ever
queues or drives a turn. A tap steers an existing binding (which agent/model it
opens with); a lifecycle event changes what the binding IS — the bot was removed
from the group, or the group turned external and may now hold people from other
organisations.

``InboundProcessor`` keeps what only it can own — the channel registry, the
owner gate on messages, the session registry and the sends — and hands this
module the three seams it needs as plain callables, so nothing here reaches back
into the processor's internals.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from coffer.application.channel.commands import ChannelCommands, SafeSend
from coffer.application.channel.ports import ChannelBinding, ChannelPeerRepoPort
from coffer.domain.channel.envelopes import InboundCallback, InboundLifecycle, InboundStop

__all__ = ["EXTERNAL_GROUP_WARNING", "InboundEvents"]

_logger = logging.getLogger(__name__)

#: Sent into a group the platform has just flagged as external. Short on
#: purpose: it interrupts whatever the group was doing, so it says what changed,
#: what Coffer will keep doing, and the one lever the owner has.
EXTERNAL_GROUP_WARNING = (
    "⚠️ This group is now an external group — people from other organisations "
    "may be in it. Coffer keeps answering here; unbind the channel if that is "
    "not what you want."
)


@dataclass(frozen=True)
class InboundEvents:
    """Handles the non-message adapter callbacks for one processor."""

    peers: ChannelPeerRepoPort
    commands: ChannelCommands
    #: The processor's owner-bound send (``InboundProcessor._safe_send``).
    safe_send: SafeSend
    #: Stops every live session of one chat — drain task cancelled, running turn
    #: interrupted. The same machinery ``unbind`` uses for a whole channel.
    stop_chat_sessions: Callable[[str, str], None]

    async def on_callback(self, binding: ChannelBinding, cb: InboundCallback) -> None:
        """A selection-card button tap. Owner-gated exactly like ``on_message``
        (an intruder in a paired group must not flip the owner's agent/model by
        tapping), then routed to the same switch the text command performs. A
        tap never pairs — an unpaired/foreign chat is ignored silently."""
        if cb.chat_kind == "group":
            # A group card is shared, exactly like a group @mention: prove the
            # tapper is the channel owner (never fall through on an empty
            # sender_id) and route the refusal back into the group/thread, not a
            # DM. A tap never bootstraps a group peer row — only the owner's
            # first @mention does — so an unrecorded group is ignored silently.
            owner = await self.peers.owner_sender_id(binding.resource_id)
            if owner is None:
                return
            if not cb.sender_id or cb.sender_id != owner:
                await self.safe_send(
                    binding,
                    cb.chat_id,
                    "🚫 Not authorized — only this channel's owner can use me here.",
                    thread_id=cb.thread_id,
                    chat_kind="group",
                )
                return
            peer = await self.peers.get_by_chat(binding.resource_id, cb.chat_id)
            if peer is None:
                return
        else:
            peer = await self.peers.get_by_chat(binding.resource_id, cb.chat_id)
            if peer is None:
                return
            if peer.sender_id is not None and cb.sender_id and peer.sender_id != cb.sender_id:
                return
        await self.commands.dispatch_callback(
            binding,
            peer,
            cb.data,
            self.safe_send,
            chat_kind=cb.chat_kind,
            thread_id=cb.thread_id,
            card_message_id=cb.platform_message_id,
        )

    async def on_lifecycle(self, binding: ChannelBinding, event: InboundLifecycle) -> None:
        """The bot's own standing in a chat changed.

        Defensive by construction: this runs on the adapter's receive loop, where
        a raise would take the whole listener down over an event that never
        drives a turn. A kind this version does not model, and an event about a
        chat with no peer row (the bot merely sat in that group — it was never
        paired, so there is nothing to tear down or warn about), are both
        ignored in silence.
        """
        peer = await self.peers.get_by_chat(binding.resource_id, event.chat_id)
        if peer is None:
            return
        if event.kind == "removed_from_group":
            await self._on_removed(binding, event)
        elif event.kind == "group_became_external":
            await self._on_became_external(binding, event)

    async def _on_removed(self, binding: ChannelBinding, event: InboundLifecycle) -> None:
        # Kicked, or the group was disbanded — either way the bot is out. Every
        # live session of that chat (its main chat and each of its threads) is
        # now driving a turn whose reply has nowhere to land, so stop them the
        # way ``unbind`` stops a whole channel's. Deliberately silent on the
        # platform: a goodbye message would just be a failed send into a group
        # the bot has already left. The owner sees it in the daemon log.
        self.stop_chat_sessions(binding.name, event.chat_id)
        _logger.warning(
            "channel.group.removed",
            extra={
                "channel": binding.name,
                "group_chat_id": event.chat_id,
                "removed_by": event.actor_display,
            },
        )

    async def _on_became_external(self, binding: ChannelBinding, event: InboundLifecycle) -> None:
        # The bot is still in the group, but its audience just grew beyond the
        # owner's own organisation — a security-relevant change to a chat the
        # owner deliberately paired. A log line alone would be invisible to the
        # person who needs it, so say it once in the group itself: the owner is
        # by definition there, and it is the one place the change is in context.
        # Answering continues — this is a heads-up, not a kill switch; unbinding
        # is the owner's call.
        _logger.warning(
            "channel.group.became_external",
            extra={
                "channel": binding.name,
                "group_chat_id": event.chat_id,
                "changed_by": event.actor_display,
            },
        )
        await self.safe_send(binding, event.chat_id, EXTERNAL_GROUP_WARNING, chat_kind="group")

    async def on_stop(self, binding: ChannelBinding, event: InboundStop, *, session: Any) -> None:
        """The user pressed the platform's own stop control (FR-063).

        Routed to exactly the path a typed ``/stop`` takes, so the two cannot
        drift apart: same cancellation, same queue pause (FR-051), same thing
        said back. Owner-gated like everything else — a stop press from a chat
        that was never paired is ignored in silence rather than answered, which
        would confirm to a stranger that this channel exists.
        """
        peer = await self.peers.get_by_chat(binding.resource_id, event.chat_id)
        if peer is None:
            return
        await self.commands.interrupt(
            binding,
            peer,
            session,
            self.safe_send,
            chat_kind=event.chat_kind,
            thread_id=event.thread_id,
        )
