"""Turn execution: handing one inbound message to the chat platform, and
rendering its turn back into the chat.

Split out of ``InboundProcessor`` to keep that module under the file-size
limit. ``TurnDriver`` owns the turn lifecycle only — ensure-conversation, the
receipt ack, queueing the message with the orchestrator, and rendering the
reply when the turn starts. Owner-gating, pairing, command dispatch, and the
session registry itself stay in ``inbound``.

A channel message does not queue here. It goes through the orchestrator's
``enqueue_message`` like a web message does, so the web's pending chips show it, the two
surfaces share one FIFO per conversation (spec chat "Queue messages sent during a
turn"), and a turn that ends on either surface advances the same queue. What the channel
keeps is an ``on_start`` sink: when the orchestrator begins the message's turn it hands
back a dedicated event queue, and the renderer spawned here drains it.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from coffer.application.channel.conversation_ops import (
    ConversationPort,
    ensure_conversation,
    explain_conversation_error,
)
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import (
    ChannelPeer,
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
)
from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.chat.attachment import Attachment
from coffer.domain.errors import CofferError

__all__ = ["QUEUE_MAX", "ConversationPort", "QueuedInbound", "Session", "TurnDriver", "TurnPort"]

_logger = logging.getLogger(__name__)

#: How many messages may wait behind a running turn before the channel says "busy" (see
#: "Answer the conversation commands from any paired chat"). The web composer is not
#: bounded; a chat's flood is.
QUEUE_MAX = 10

#: Sends one reply back through a channel binding, matching
#: ``ephemeral.safe_send``'s signature (buttons omitted — turn driving never
#: sends a selection card).
SafeSend = Callable[..., Awaitable[None]]

#: Looks up (creating if absent) the session keyed by (channel, chat_id,
#: thread_id) — the same registry ``InboundProcessor`` uses.
SessionAccessor = Callable[[str, str, str], "Session"]


@dataclass(frozen=True)
class QueuedInbound:
    """One inbound message, ready to become a turn.

    ``text`` drives the turn (it opens with the origin block of "Open every turn with
    its message origin"); ``attachments`` are the downloaded files to materialise for
    the agent; ``thread_id`` / ``chat_kind`` route the reply back to where the message
    came from; ``reply_to_message_id`` is the user's inbound platform_message_id the
    receipt/completion reactions target (see "Acknowledge receipt and completion by
    capability"; "" when the transport supplied none); the mention id and address are
    what a group reply opens by @mentioning (see "Mention the asker in a group answer");
    and ``title_hint`` is the human's own words, carried apart from the driving text
    (spec chat "Persist conversations and messages in SQLite"; "" when nothing was
    nameable).
    """

    text: str
    attachments: tuple[Attachment, ...] = ()
    thread_id: str = ""
    chat_kind: str = "direct"
    reply_to_message_id: str = ""
    mention_user_id: str = ""
    mention_user_email: str = ""
    title_hint: str = ""


class TurnPort(Protocol):
    """The slice of the turn orchestrator we use."""

    async def enqueue_message(
        self,
        conversation_id: str,
        user_text: str,
        *,
        attachments: Sequence[Attachment] = (),
        title_hint: str | None = None,
        on_start: Callable[[asyncio.Queue[Any]], None] | None = None,
    ) -> bool: ...

    def pending(self, conversation_id: str) -> list[str]: ...

    def interrupt_turn(self, conversation_id: str) -> None: ...


@dataclass
class Session:
    # The conversation whose turn is rendering right now (None between turns).
    # Tracked separately from the peer's active conversation: ``/new`` rebinds
    # the peer while a turn keeps running on the old conversation, so ``/stop``
    # and unbind must target the turn that is actually running.
    running_conversation_id: str | None = None
    # The renderer draining that turn's events into the chat.
    render_task: asyncio.Task[None] | None = None
    # The most recently received document/attachment for this (channel, chat, thread),
    # held for a `/save` that follows (spec channels "Save a sent document into a
    # collection"). It rides alongside the ordinary turn — an attachment still reaches
    # the agent exactly as before; this is ONLY the channel's own memory of what a later
    # `/save` acts on. Replaced by the next attachment that arrives here, and cleared
    # once a save is attempted (succeeding or not — retrying the same bytes against the
    # same failure is never useful).
    pending_document: Attachment | None = None


class TurnDriver:
    """Hands inbound messages to the chat platform and renders their turns."""

    def __init__(
        self,
        *,
        peers: ChannelPeerRepoPort,
        threads: ChannelThreadConversationRepoPort,
        conversations: ConversationPort,
        turns: TurnPort,
        safe_send: SafeSend,
        session: SessionAccessor,
    ) -> None:
        self._peers = peers
        self._threads = threads
        self._conversations = conversations
        self._turns = turns
        self._safe_send = safe_send
        self._session = session

    async def submit(self, binding: ChannelBinding, peer: ChannelPeer, item: QueuedInbound) -> None:
        """Queue ``item`` as a turn on this thread's conversation.

        The turn starts now when the conversation is idle, else waits its turn behind
        the messages already pending — web and channel alike, in arrival order (spec
        chat "Queue messages sent during a turn"). Past ``QUEUE_MAX`` pending the
        message is dropped and the chat told (see "Answer the conversation commands from
        any paired chat"): a flood must not pile up forever.
        """
        adapter = binding.adapter

        async def _say(text: str) -> None:
            await self._safe_send(
                binding, peer.chat_id, text, thread_id=item.thread_id, chat_kind=item.chat_kind
            )

        try:
            conversation_id = await ensure_conversation(
                self._conversations, self._threads, binding, peer, item.thread_id
            )
        except CofferError as e:
            # e.g. the channel's default agent is unknown/misconfigured — the
            # owner must see it in the chat, not only in the daemon log.
            await _say(explain_conversation_error(e))
            return
        if len(self._turns.pending(conversation_id)) >= QUEUE_MAX:
            await _say("⚠️ Busy — message dropped, try again.")
            return
        # An immediate receipt ack (👀) on the user's message where the
        # transport supports reactions (Telegram); SeaTalk has none and leans on
        # the typing signal the renderer sends. Best-effort — a failed ack never
        # breaks the turn. At receipt, not at start: a queued message was heard
        # too.
        if adapter.capabilities.supports_reactions and item.reply_to_message_id:
            with contextlib.suppress(Exception):
                await adapter.set_reaction(peer.chat_id, item.reply_to_message_id, "👀")

        def on_start(queue: asyncio.Queue[Any]) -> None:
            self._spawn_render(binding, peer, item, conversation_id, queue)

        try:
            # ``text`` opens with the turn's context blocks (origin, thread
            # history); ``title_hint`` is the human's own words out of the same
            # message, so a conversation still under its placeholder title is
            # named after what the person asked and not after a header every
            # channel turn shares (spec chat "Persist conversations and messages in SQLite").
            await self._turns.enqueue_message(
                conversation_id,
                item.text,
                attachments=item.attachments,
                title_hint=item.title_hint,
                on_start=on_start,
            )
        except CofferError as e:
            await _say(f"⚠️ {e} [{e.code}]")

    def _spawn_render(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        item: QueuedInbound,
        conversation_id: str,
        queue: asyncio.Queue[Any],
    ) -> None:
        """The orchestrator began this message's turn: render it into the chat."""
        session = self._session(binding.resource.name, peer.chat_id, item.thread_id)
        task = asyncio.create_task(
            self._render(binding, peer, item, conversation_id, queue, session),
            name=f"channel-render:{binding.resource.name}:{peer.chat_id}:{item.thread_id}",
        )
        # Track the live turn so /stop and unbind can target it even after /new
        # rebinds the peer to a fresh conversation mid-turn.
        session.render_task = task
        session.running_conversation_id = conversation_id

    async def _render(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        item: QueuedInbound,
        conversation_id: str,
        queue: asyncio.Queue[Any],
        session: Session,
    ) -> None:
        adapter = binding.adapter
        if adapter.capabilities.supports_typing:
            with contextlib.suppress(Exception):
                await adapter.send_typing(
                    peer.chat_id, thread_id=item.thread_id, chat_kind=item.chat_kind
                )

        async def _send(message: str) -> None:
            # The turn's own replies point back at the message that
            # drove them (the helper drops the pointer outside a group).
            await self._safe_send(
                binding,
                peer.chat_id,
                message,
                thread_id=item.thread_id,
                chat_kind=item.chat_kind,
                reply_to_message_id=item.reply_to_message_id,
            )

        renderer = TurnRenderer(
            channel=binding.resource.name,
            adapter=adapter,
            chat_id=peer.chat_id,
            conversation_id=conversation_id,
            send=_send,
            thread_id=item.thread_id,
            chat_kind=item.chat_kind,
            mention_user_id=item.mention_user_id,
            mention_user_email=item.mention_user_email,
        )
        clean = False
        try:
            clean = await renderer.consume(queue)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("channel.turn.failed", extra={"channel": binding.resource.name})
        finally:
            # The next turn's renderer may already have been spawned (the queue
            # advances the moment a turn ends); only the renderer on record
            # clears the slot, so it never erases a successor's.
            if session.render_task is asyncio.current_task():
                session.render_task = None
                session.running_conversation_id = None
        # Mark completion (✅) on the user's message ONLY on a clean finish
        # (an errored/interrupted turn keeps just the 👀 receipt), where the
        # transport supports reactions. Best-effort — never fails a delivered reply.
        if clean and adapter.capabilities.supports_reactions and item.reply_to_message_id:
            with contextlib.suppress(Exception):
                await adapter.set_reaction(peer.chat_id, item.reply_to_message_id, "✅")
