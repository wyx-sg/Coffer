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
from coffer.application.channel.reply_tracking import ReplyTracker
from coffer.application.channel.store_ports import (
    ChannelPeer,
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
    ReplyLedgerPort,
)
from coffer.application.channel.turn_finish import TurnOutcome, failure_line
from coffer.application.channel.turn_render import TurnRenderer
from coffer.application.runtime.supervisor import spawn
from coffer.domain.channel.envelopes import ChoiceButton, SentMessage
from coffer.domain.chat.attachment import Attachment
from coffer.domain.errors import CofferError

__all__ = [
    "DROPPED_NOTICE",
    "QUEUE_MAX",
    "ConversationPort",
    "QueuedInbound",
    "Session",
    "TurnDriver",
    "TurnPort",
    "queued_notice",
]

_logger = logging.getLogger(__name__)

#: How many messages may wait behind a running turn (see "Answer the conversation
#: commands from any paired chat"): up to this many are queued and told "Queued (n)";
#: only one arriving past it is dropped, with the reason. The web composer is not
#: bounded; a chat's flood is.
QUEUE_MAX = 10


def queued_notice() -> str:
    """What a message that joined the queue behind a running one is told. The
    limit is mentioned only when a message is actually dropped over it."""
    return "⏳ Queued — runs when the current one finishes."


#: What a message arriving with the queue already full is told: dropped, and why.
DROPPED_NOTICE = (
    f"⚠️ Not queued — {QUEUE_MAX} messages are already waiting, so this one was dropped. "
    "Send it again once they have run, or /stop."
)

#: Sends one reply back through a channel binding, matching
#: ``ephemeral.safe_send``'s signature (buttons omitted — turn driving never
#: sends a selection card).
SafeSend = Callable[..., Awaitable[Any]]

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
    what a group reply opens by @mentioning (see "Mention the asker in a group answer"),
    with the display name a platform that spells mentions by name needs;
    and ``title_hint`` is the human's own words, carried apart from the driving text
    (spec chat "Persist conversations and messages in SQLite"; "" when nothing was
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
        replies: ReplyLedgerPort,
    ) -> None:
        self._peers = peers
        self._threads = threads
        self._conversations = conversations
        self._turns = turns
        self._safe_send = safe_send
        self._session = session
        self._replies = replies

    async def acknowledge(
        self, binding: ChannelBinding, peer: ChannelPeer, item: QueuedInbound
    ) -> None:
        """Say "heard" the moment a message arrives — before its burst window closes
        (see "Take a burst of messages as one turn") and before a queued turn starts: a
        👀 reaction where the transport has reactions (Telegram), else the typing signal
        (SeaTalk). Best-effort — a failed ack never breaks the turn (see "Acknowledge
        receipt and completion by capability")."""
        adapter = binding.adapter
        with contextlib.suppress(Exception):
            if adapter.capabilities.supports_reactions and item.reply_to_message_id:
                await self._react(binding, peer, item, adapter.capabilities.reactions.received)
            elif adapter.capabilities.supports_typing:
                await adapter.send_typing(
                    peer.chat_id, thread_id=item.thread_id, chat_kind=item.chat_kind
                )

    async def submit(self, binding: ChannelBinding, peer: ChannelPeer, item: QueuedInbound) -> None:
        """Queue ``item`` as a turn on this thread's conversation.

        The turn starts now when the conversation is idle, else waits its turn behind
        the messages already pending — web and channel alike, in arrival order (spec
        chat "Queue messages sent during a turn"). A message that waits is told its
        notice ("Queued"); past ``QUEUE_MAX`` pending the message is dropped and the
        chat told why (see "Answer the conversation commands from any paired chat"): a
        flood must not pile up forever.
        """

        async def _say(text: str) -> None:
            await self._safe_send(
                binding, peer.chat_id, text, thread_id=item.thread_id, chat_kind=item.chat_kind
            )

        try:
            conversation_id = await ensure_conversation(
                self._conversations,
                self._threads,
                binding,
                peer,
                item.conversation_thread_id,
                chat_kind=item.chat_kind,
                idle_hours=binding.new_conversation_after_idle_hours,
                say=_say,
            )
        except CofferError as e:
            # e.g. the default agent is unknown/misconfigured: say so in the chat.
            await _say(explain_conversation_error(e))
            return
        if len(self._turns.pending(conversation_id)) >= QUEUE_MAX:
            await _say(DROPPED_NOTICE)
            return

        def on_start(queue: asyncio.Queue[Any]) -> None:
            self._spawn_render(binding, peer, item, conversation_id, queue)

        try:
            # ``text`` opens with the turn's context blocks (origin, thread
            # history); ``title_hint`` is the human's own words out of the same
            # message, so a conversation still under its placeholder title is
            # named after what the person asked and not after a header every
            # channel turn shares (spec chat "Persist conversations and messages in SQLite").
            queued = await self._turns.enqueue_message(
                conversation_id,
                item.text,
                attachments=item.attachments,
                title_hint=item.title_hint,
                on_start=on_start,
            )
        except CofferError as e:
            await _say(failure_line(str(e)))
            return
        if queued:
            await _say(queued_notice())

    def render_sink(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        item: QueuedInbound,
        conversation_id: str,
    ) -> Callable[[asyncio.Queue[Any]], None]:
        """An ``on_start`` sink that renders the turn into ``item``'s chat/thread
        exactly like a channel-driven turn — for a turn another surface queued on
        a channel's conversation (spec chat "Mirror a web reply into the channel
        it came from")."""

        def on_start(queue: asyncio.Queue[Any]) -> None:
            self._spawn_render(binding, peer, item, conversation_id, queue)

        return on_start

    def _spawn_render(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        item: QueuedInbound,
        conversation_id: str,
        queue: asyncio.Queue[Any],
    ) -> None:
        """The orchestrator began this message's turn: render it into the chat."""
        # Keyed by the conversation, so `/stop` from anywhere that conversation is
        # reached finds its running turn; the task name says where it renders.
        session = self._session(binding.resource.uid, peer.chat_id, item.conversation_thread_id)
        task = spawn(
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
        # The turn is running now (a queued message kept its receipt mark until here).
        await self._react(binding, peer, item, adapter.capabilities.reactions.working)

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

        async def _send_card(
            text: str, buttons: Sequence[ChoiceButton], *, title: str = ""
        ) -> SentMessage | None:
            sent: SentMessage | None = await self._safe_send(
                binding,
                peer.chat_id,
                text,
                buttons=buttons,
                title=title,
                thread_id=item.thread_id,
                chat_kind=item.chat_kind,
                reply_to_message_id=item.reply_to_message_id,
            )
            return sent

        # What the reply turns out to be, so ``/del`` and the 🗑 button can take it back.
        tracker = ReplyTracker.for_turn(
            self._replies, binding, peer.chat_id, item.thread_id, item.chat_kind, _send_card
        )
        renderer = TurnRenderer(
            channel=binding.resource.name,
            adapter=adapter,
            chat_id=peer.chat_id,
            conversation_id=conversation_id,
            send=_send,
            send_card=_send_card,
            thread_id=item.thread_id,
            chat_kind=item.chat_kind,
            mention_user_id=item.mention_user_id,
            mention_user_email=item.mention_user_email,
            mention_user_name=item.mention_user_name,
            show_steps=binding.show_steps,
            notify_after_seconds=binding.notify_after_seconds,
            tracker=tracker,
        )
        outcome: TurnOutcome = "failed"
        try:
            outcome = await renderer.consume(queue)
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
        # Mark how it ended on the user's message: done, failed or stopped.
        marks = adapter.capabilities.reactions
        mark = {"failed": marks.failed, "stopped": marks.stopped}.get(outcome, marks.done)
        await self._react(binding, peer, item, mark)

    async def _react(
        self, binding: ChannelBinding, peer: ChannelPeer, item: QueuedInbound, emoji: str
    ) -> None:
        """Set one progress mark on the asker's message, where the transport
        reacts and names an emoji for this stage. Best-effort — a failed mark
        never fails a delivered reply (see "Acknowledge receipt and completion
        by capability")."""
        adapter = binding.adapter
        if not (emoji and adapter.capabilities.supports_reactions):
            return
        # Every message the turn answers, the merged burst's earlier ones included.
        for message_id in (*item.earlier_message_ids, item.reply_to_message_id):
            if not message_id:
                continue
            with contextlib.suppress(Exception):
                await adapter.set_reaction(peer.chat_id, message_id, emoji)

    async def mark_stopped(
        self, binding: ChannelBinding, peer: ChannelPeer, items: Sequence[QueuedInbound]
    ) -> None:
        """Put the stopped mark on messages a ``/stop`` discarded before they
        became a turn: they were acknowledged on arrival and would otherwise stay
        on their receipt mark for good."""
        marks = binding.adapter.capabilities.reactions
        for item in items:
            await self._react(binding, peer, item, marks.stopped)
