"""The shared inbound pipeline: every channel's messages flow through here.

owner gate → pairing claim → commands → conversation mapping → the chat
platform's own queue (execution lives in ``turn_driver``, rendering in
``turn_render``).

The chat platform is reached only through its public seams (conversation
service + turn orchestrator), exactly like the web UI: agents cannot tell a
channel turn from a UI turn, and a new agent provider is reachable from every
channel with no code here changing. Slash-command handling lives in
``commands``, conversation creation in ``conversation_ops``, running a
queued turn end-to-end in ``turn_driver``, deciding what is a command in
``inbound_commands``, and the two inbound callbacks that
never drive a turn (a card tap, a chat-lifecycle event) in ``inbound_events``.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Sequence

from coffer.application.audit_service import AuditService
from coffer.application.channel.commands import ChannelCommands
from coffer.application.channel.ephemeral import safe_send
from coffer.application.channel.inbound_burst import BurstPart, InboundBurst, window_for
from coffer.application.channel.inbound_commands import route_slash
from coffer.application.channel.inbound_events import InboundEvents
from coffer.application.channel.inbound_gate import group_peer
from coffer.application.channel.pairing import PairingManager, claim_pairing
from coffer.application.channel.parallel_threads import resolve_conversation_thread_id
from coffer.application.channel.ports import (
    AgentCatalogPort,
    ChannelBinding,
    ModelSuggestionPort,
)
from coffer.application.channel.save_ports import CollectionCatalogPort, IngestPort
from coffer.application.channel.store_ports import (
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
)
from coffer.application.channel.turn_context import fold_turn_context
from coffer.application.channel.turn_driver import (
    ConversationPort,
    QueuedInbound,
    TurnDriver,
    TurnPort,
)
from coffer.application.channel.turn_driver import (
    Session as _Session,
)
from coffer.application.channel.turn_media import conversation_title_hint
from coffer.domain.channel.envelopes import (
    InboundCallback,
    InboundLifecycle,
    InboundMessage,
    InboundStop,
)
from coffer.domain.channel.rich_content import format_origin
from coffer.domain.chat.attachment import Attachment, attachment_note

__all__ = ["ChannelBinding", "InboundProcessor"]

_logger = logging.getLogger(__name__)


class InboundProcessor:
    """Owner-gated bridge from adapter callbacks to chat-platform turns."""

    def __init__(
        self,
        *,
        peers: ChannelPeerRepoPort,
        threads: ChannelThreadConversationRepoPort,
        pairing: PairingManager,
        conversations: ConversationPort,
        turns: TurnPort,
        audit: AuditService,
        agents: AgentCatalogPort,
        model_suggestions: ModelSuggestionPort,
        collections: CollectionCatalogPort,
        ingest: IngestPort,
        knowledge_enabled: Callable[[], bool] = lambda: True,
    ) -> None:
        self._peers = peers
        self._threads = threads
        self._pairing = pairing
        self._conversations = conversations
        self._turns = turns
        self._audit = audit
        self._bindings: dict[str, ChannelBinding] = {}
        # Keyed by (channel, chat_id, conversation thread): one peer's DM, one
        # group's main chat, each of that group's threads and each parallel
        # thread render their own turn.
        self._sessions: dict[tuple[str, str, str], _Session] = {}
        self._commands = ChannelCommands(
            threads=threads,
            conversations=conversations,
            turns=turns,
            agents=agents,
            model_suggestions=model_suggestions,
            collections=collections,
            ingest=ingest,
            knowledge_enabled=knowledge_enabled,
            running_in=self._running_in,
            running_in_chat=self._running_in_chat,
        )
        self._turn_driver = TurnDriver(
            peers=peers,
            threads=threads,
            conversations=conversations,
            turns=turns,
            safe_send=safe_send,
            session=self._session,
        )
        # Each chat/thread's burst, held until quiet ("Take a burst of messages as one turn").
        self._burst = InboundBurst(lambda ctx, item: self._turn_driver.submit(ctx[0], ctx[1], item))
        self._events = InboundEvents(
            peers=peers,
            commands=self._commands,
            safe_send=safe_send,
            stop_chat_sessions=self._stop_chat_sessions,
            session=self._session,
        )

    # -- runtime registry ------------------------------------------------

    def bind(self, binding: ChannelBinding) -> None:
        self._bindings[binding.resource.name] = binding

    def unbind(self, name: str) -> None:
        self._bindings.pop(name, None)
        self._burst.drop_channel(name)
        # A channel can have many live sessions (its DM, each group, each
        # thread within a group) — unbinding it must stop every one of them,
        # not just a single legacy session.
        self._stop_sessions([key for key in self._sessions if key[0] == name])

    def _stop_chat_sessions(self, channel: str, chat_id: str) -> None:
        """Stop ONE chat's live sessions (a group's main chat and each of its
        threads) — for when the bot loses that chat while its channel lives on."""
        self._stop_sessions(
            [key for key in self._sessions if key[0] == channel and key[1] == chat_id]
        )

    def _stop_sessions(self, keys: Sequence[tuple[str, str, str]]) -> None:
        for key in keys:
            session = self._sessions.pop(key, None)
            if session is None:
                continue
            if session.render_task is not None:
                session.render_task.cancel()
            # Cancelling the renderer only stops delivery; the orchestrator turn keeps
            # running and would deliver its reply to the web UI alone, leaving the bot
            # silent. Interrupt the live turn so its partial reply is the contract — not
            # a turn that completes undelivered. (The interrupt also pauses the
            # conversation's queue, spec chat "Pause the pending queue on interrupt", so
            # nothing queued behind it runs into a bot that is gone.)
            if session.running_conversation_id is not None:
                with contextlib.suppress(Exception):
                    self._turns.interrupt_turn(session.running_conversation_id)
                session.running_conversation_id = None

    def binding(self, name: str) -> ChannelBinding | None:
        return self._bindings.get(name)

    @property
    def turn_driver(self) -> TurnDriver:
        """What renders a turn into a chat — also for a web-queued turn."""
        return self._turn_driver

    def shutdown(self) -> None:
        for name in list(self._bindings):
            self.unbind(name)
        self._bindings.clear()

    # -- adapter callbacks -------------------------------------------------

    async def on_message(self, msg: InboundMessage) -> None:
        binding = self._bindings.get(msg.channel)
        if binding is None:
            return
        if msg.chat_kind == "group":
            peer = await group_peer(self._peers, binding, msg)
            if peer is None:
                return
        else:
            peer = await self._peers.get_by_chat(binding.resource.id, msg.chat_id)
            if peer is None:
                await self._maybe_pair(binding, msg)
                return
            if peer.sender_id is not None and msg.sender_id and peer.sender_id != msg.sender_id:
                # Right chat (e.g. a paired group), wrong member — ignore silently.
                # Never fall through to pairing: an intruder must not be able to
                # re-pair the channel by sending a code into the owner's chat. A
                # message with no sender id (the transport could not supply one)
                # falls back to the chat-id match already passed, so a quirk in one
                # update shape never locks the owner out of their own channel.
                return
        # Which conversation this message joins; ``msg.thread_id`` stays where the
        # reply goes (see "Key conversation identity by channel, chat and thread").
        conv_thread = await resolve_conversation_thread_id(
            self._threads, binding, msg.chat_id, chat_kind=msg.chat_kind, thread_id=msg.thread_id
        )
        text = msg.text.strip()
        attachments = tuple(
            Attachment(path=a.path, mime=a.mime, filename=a.filename) for a in msg.attachments
        )
        # spec chat "Persist conversations and messages in SQLite": taken where the
        # person's own message is still intact — before the context blocks below fold
        # in, and from this message's own files.
        title_hint = conversation_title_hint(text, attachments)
        if attachments:
            # Remember it (owner-gated already) for a `/kb` that follows (spec channels
            # "Save a sent document into a collection") — never the thread-history files
            # folded in below. One slot, first file only: the ingest service takes one
            # file per call (spec knowledge "Bound uploads and leave nothing behind on failure").
            session = self._session(binding.resource.name, peer.chat_id, conv_thread)
            session.pending_document = attachments[0]
        # A command (or a near miss of one) is decided on the message's OWN text,
        # before any thread history is folded in (see ``inbound_commands``).
        if await route_slash(
            commands=self._commands,
            burst=self._burst,
            session=self._session,
            binding=binding,
            peer=peer,
            msg=msg,
            text=text,
            has_attachments=bool(attachments),
            conversation_thread_id=conv_thread,
        ):
            return
        # The thread it landed in and the message it quotes ground the turn
        # (see "Ground a turn in the message it quotes").
        text, attachments = await fold_turn_context(binding, msg, text, attachments)
        if not text and not attachments:
            # An empty envelope with nothing downloadable (a sticker, a location,
            # a media type the transport does not extract) — and no thread
            # history/images to ground a turn on either.
            await safe_send(
                binding,
                peer.chat_id,
                "⚠️ Unsupported message — send text, a photo, or a file.",
                thread_id=msg.thread_id,
                chat_kind=msg.chat_kind,
            )
            return
        # "Open every turn with its message origin": provenance (platform, chat, thread,
        # sender) rides on every turn, added after command detection and the empty
        # check; the message id is what the receipt/completion reactions target and
        # the mention id what a group answer opens with ("Mention the asker in a group
        # answer"). A media message with no caption still needs non-blank text.
        item = QueuedInbound(
            text="",
            attachments=attachments,
            thread_id=msg.thread_id,
            chat_kind=msg.chat_kind,
            reply_to_message_id=msg.platform_message_id,
            mention_user_id=msg.sender_mention_id,
            mention_user_email=msg.sender_mention_email,
            mention_user_name=msg.sender_display,
            title_hint=title_hint,
            conversation_thread_id=conv_thread,
        )
        await self._turn_driver.acknowledge(binding, peer, item)
        self._burst.add(
            (binding.resource.name, peer.chat_id, msg.thread_id),
            (binding, peer),
            BurstPart(
                origin=format_origin(msg, platform=binding.channel_type),
                body=text or attachment_note(attachments),
                item=item,
                window=window_for(binding, msg),
            ),
        )

    async def on_callback(self, cb: InboundCallback) -> None:
        """A selection-card button tap (handled in ``inbound_events``)."""
        binding = self._bindings.get(cb.channel)
        if binding is None:
            return
        conv_thread = await resolve_conversation_thread_id(
            self._threads, binding, cb.chat_id, chat_kind=cb.chat_kind, thread_id=cb.thread_id
        )
        await self._events.on_callback(binding, cb, conversation_thread_id=conv_thread)

    async def on_lifecycle(self, event: InboundLifecycle) -> None:
        """The bot's standing in a chat changed — removed from a group, or the
        group turned external (handled in ``inbound_events``, never a turn)."""
        binding = self._bindings.get(event.channel)
        if binding is None:
            return
        await self._events.on_lifecycle(binding, event)

    async def on_stop(self, event: InboundStop) -> None:
        """The user pressed the platform's own stop control (see
        "Stop the turn from the platform's own stop control")."""
        binding = self._bindings.get(event.channel)
        if binding is None:
            return
        conv_thread = await resolve_conversation_thread_id(
            self._threads,
            binding,
            event.chat_id,
            chat_kind=event.chat_kind,
            thread_id=event.thread_id,
        )
        await self._burst.drop((event.channel, event.chat_id, event.thread_id))
        await self._events.on_stop(
            binding,
            event,
            session=self._session(event.channel, event.chat_id, conv_thread),
            conversation_thread_id=conv_thread,
        )

    # -- pairing -----------------------------------------------------------

    async def _maybe_pair(self, binding: ChannelBinding, msg: InboundMessage) -> None:
        peer = await claim_pairing(
            binding,
            text=msg.text,
            chat_id=msg.chat_id,
            sender_display=msg.sender_display,
            sender_id=msg.sender_id,
            pairing=self._pairing,
            peers=self._peers,
            audit=self._audit,
        )
        if peer is None:
            return
        await safe_send(
            binding,
            msg.chat_id,
            f"✅ Paired. This chat now controls Coffer channel '{binding.resource.name}'.",
        )
        # Then the commands, once, as a card where the transport has buttons
        # (spec channels "Offer the commands as a help card").
        await self._commands.send_help(binding, peer, safe_send)

    # -- helpers ---------------------------------------------------------------

    def _running_in(self, channel: str, chat_id: str, thread_id: str) -> str | None:
        session = self._sessions.get((channel, chat_id, thread_id))
        return session.running_conversation_id if session is not None else None

    def _running_in_chat(self, channel: str, chat_id: str) -> list[str]:
        """Every conversation rendering a turn anywhere in one chat."""
        return [
            session.running_conversation_id
            for key, session in self._sessions.items()
            if key[0] == channel and key[1] == chat_id and session.running_conversation_id
        ]

    def _session(self, channel: str, chat_id: str, thread_id: str) -> _Session:
        key = (channel, chat_id, thread_id)
        if key not in self._sessions:
            self._sessions[key] = _Session()
        return self._sessions[key]
