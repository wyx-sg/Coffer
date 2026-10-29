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
from functools import partial
from typing import Any, Protocol

from coffer.application.channel import turn_origin
from coffer.application.channel.conversation_ops import (
    ConversationPort,
    ensure_conversation,
    explain_conversation_error,
)
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.queued_inbound import QueuedInbound, origin_of_turn
from coffer.application.channel.reply_tracking import ReplyTracker
from coffer.application.channel.rewrite_turn import start_rewrite
from coffer.application.channel.scheduled_turn import run_outcome
from coffer.application.channel.store_ports import (
    ChannelPeer,
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
    ReplyLedgerPort,
    ThreadCursorPort,
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
]

_logger = logging.getLogger(__name__)

#: How many messages may wait behind a running turn (see "Answer the conversation
#: commands from any paired chat"): up to this many are queued silently;
#: only one arriving past it is dropped, with the reason. The web composer is not
#: bounded; a chat's flood is.
QUEUE_MAX = 10


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

    def interrupt_turn(self, conversation_id: str) -> bool: ...


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
        cursors: ThreadCursorPort,
    ) -> None:
        self._peers = peers
        self._cursors = cursors
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
        chat "Queue messages sent during a turn"). A message that waits is not
        answered (it runs in turn); past ``QUEUE_MAX`` pending the message is
        dropped and the chat told why (see "Answer the conversation commands from any
        paired chat"): a flood must not pile up forever.
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
            )
        except CofferError as e:
            # e.g. the default agent is unknown/misconfigured: say so in the chat.
            await _say(explain_conversation_error(e))
            return
        if item.thread_id:
            # The thread cursor taken before the conversation existed is its now
            # (spec channels "Ground a thread turn in a bounded slice of the thread").
            await self._cursors.claim(
                binding.resource.uid, peer.chat_id, item.thread_id, conversation_id
            )
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
            # channel turn shares (spec chat "Keep the conversation index without its text").
            await self._turns.enqueue_message(
                conversation_id,
                item.text,
                attachments=item.attachments,
                title_hint=item.title_hint,
                on_start=on_start,
            )
        except CofferError as e:
            await _say(failure_line(str(e)))
            return

    async def submit_scheduled(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        item: QueuedInbound,
        conversation_id: str,
    ) -> None:
        """Queue a scheduled run's turn on ``conversation_id``, which the runner
        has already chosen (continued or freshly opened). It waits behind
        whatever the conversation is doing, like any message; ``ValueError``
        says why it could not be queued, and a ``CofferError`` from the
        orchestrator passes through. The runner tells the chat."""
        if len(self._turns.pending(conversation_id)) >= QUEUE_MAX:
            raise ValueError(f"{QUEUE_MAX} messages are already waiting in this conversation")

        def on_start(queue: asyncio.Queue[Any]) -> None:
            self._spawn_render(binding, peer, item, conversation_id, queue)

        await self._turns.enqueue_message(
            conversation_id, item.text, title_hint=item.title_hint, on_start=on_start
        )

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
        # A reply too long for the chat is said again short by a follow-up turn.
        render = partial(self._spawn_render, binding, peer)
        rewrite = partial(start_rewrite, self._turns, conversation_id, item, render=render)
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
            tracker=tracker,
            rewrite=None if item.rewrite else rewrite,
            offer_full_report=item.rewrite,
            silent_mark=item.scheduled is not None,
        )
        outcome: TurnOutcome = "failed"
        origin = origin_of_turn(binding.resource.uid, peer.chat_id, item)
        turn_origin.remember(conversation_id, origin)
        try:
            outcome = await renderer.consume(queue)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("channel.turn.failed", extra={"channel": binding.resource.name})
        finally:
            turn_origin.forget(conversation_id, origin)
            if item.scheduled is not None:
                silenced = renderer.silenced
                with contextlib.suppress(Exception):
                    await item.scheduled.on_end(
                        run_outcome(outcome, silenced=silenced), renderer.error_text
                    )
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
