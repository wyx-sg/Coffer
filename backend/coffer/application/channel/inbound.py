"""The shared inbound pipeline: every channel's messages flow through here.

owner gate → pairing claim → commands → conversation mapping → the chat
platform's own queue (execution lives in ``turn_driver``, rendering in
``turn_render``).

The chat platform is reached only through its public seams (conversation
service + turn orchestrator), exactly like the web UI: agents cannot tell a
channel turn from a UI turn, and a new agent provider is reachable from every
channel with no code here changing. Slash-command handling lives in
``commands``, conversation creation in ``conversation_ops``, running a
queued turn end-to-end in ``turn_driver``, and the two inbound callbacks that
never drive a turn (a card tap, a chat-lifecycle event) in ``inbound_events``.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from coffer.application.audit_service import AuditService
from coffer.application.channel.commands import HELP_TEXT, ChannelCommands
from coffer.application.channel.ephemeral import (
    private_send,
    safe_send,
    target_for_command,
)
from coffer.application.channel.inbound_events import InboundEvents
from coffer.application.channel.pairing import PairingManager, claim_pairing
from coffer.application.channel.ports import (
    AgentCatalogPort,
    ChannelBinding,
    ModelSuggestionPort,
)
from coffer.application.channel.save_ports import CollectionCatalogPort, IngestPort
from coffer.application.channel.store_ports import (
    ChannelPeer,
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
        # Keyed by (channel, chat_id, thread_id): one peer's DM, one group's
        # main chat, and each of that group's threads each render their own turn.
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
        )
        self._turn_driver = TurnDriver(
            peers=peers,
            threads=threads,
            conversations=conversations,
            turns=turns,
            safe_send=safe_send,
            session=self._session,
        )
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
            if binding.require_mention and not msg.addressed:
                # Un-addressed group chatter (no @mention/reply-to-bot) is
                # never a turn — a bot must not speak up uninvited in a group
                # it merely sits in. With ``require_mention`` off the channel
                # lets un-addressed group messages through this gate (still
                # owner-gated by the sender_id checks below).
                return
            if binding.ignore_other_mentions and msg.mentions_others:
                # "Configure when the bot answers in a group": a group message that
                # @mentions another user is aimed at a human — drop it silently (no
                # reply), before the owner gate, so a bot in a busy group never butts in
                # regardless of who sent it.
                return
            owner = await self._peers.owner_sender_id(binding.resource.id)
            if owner is None:
                # The channel has never been paired (no DM/group has a known
                # owner sender id yet) — a group @mention cannot bootstrap
                # pairing; only the paired DM/pairing-code flow can.
                return
            if not msg.sender_id or msg.sender_id != owner:
                # A group chat is shared, unlike a DM's 1:1 chat_id match — an
                # empty sender_id here (the transport failed to supply one)
                # must never fall through as "assume it's the owner": that
                # would let any member without a resolvable sender_id drive
                # turns on the owner's agent. Refuse whenever ownership can't
                # be proven, not just when it is provably wrong.
                await safe_send(
                    binding,
                    msg.chat_id,
                    "🚫 Not authorized — only this channel's owner can use me here.",
                    thread_id=msg.thread_id,
                    chat_kind="group",
                )
                return
            peer = await self._peers.get_by_chat(binding.resource.id, msg.chat_id)
            if peer is None:
                # First @mention from the owner in this group/thread — record
                # a peer row for it so future turns (and /commands) resolve a
                # conversation scoped to this chat, not the owner's DM.
                peer = ChannelPeer(
                    resource_id=binding.resource.id,
                    chat_id=msg.chat_id,
                    display_name=msg.sender_display,
                    paired_at=datetime.now(tz=UTC),
                    sender_id=owner,
                )
                await self._peers.upsert(peer)
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
        text = msg.text.strip()
        attachments = tuple(
            Attachment(path=a.path, mime=a.mime, filename=a.filename) for a in msg.attachments
        )
        # spec chat "Persist conversations and messages in SQLite": taken where the
        # person's own message is still intact — before the context blocks below fold
        # in, and from this message's own files.
        title_hint = conversation_title_hint(text, attachments)
        if attachments:
            # Remember it (owner-gated already) for a `/save` that follows (spec
            # channels "Save a sent document into a collection") — never the
            # thread-history attachments folded in below. The turn below still runs
            # unchanged; `/save` only ALSO makes this saveable. One slot, first file
            # only: the ingest service takes one file per call (spec knowledge "Bound
            # uploads and leave nothing behind on failure").
            session = self._session(binding.resource.name, peer.chat_id, msg.thread_id)
            session.pending_document = attachments[0]
        # A slash command is text-only; a caption starting with "/" alongside an
        # attachment is a normal message, not a command. Decide on the message's
        # OWN text/attachments, before any thread history is folded in (a
        # command never fetches thread context).
        is_command = text.startswith("/") and not attachments
        if not is_command:
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
        if is_command:
            await self._commands.handle(
                binding,
                peer,
                text,
                self._session(binding.resource.name, peer.chat_id, msg.thread_id),
                # A command answer is the asker's business, not the room's (see
                # "Keep non-answer chatter private in a group").
                private_send(safe_send, target_for_command(msg, text)),
                chat_kind=msg.chat_kind,
                thread_id=msg.thread_id,
            )
            return
        # A media message with no caption still needs non-blank text to persist. "Open
        # every turn with its message origin": the turn opens with its own provenance
        # (platform, chat kind + title + id, thread, sender) so the agent knows which
        # group/thread it is answering in instead of inferring it from the bot's group
        # list. Folded in AFTER command detection (a prefixed "/help" would stop being a
        # command) and after the empty-envelope check (a header is not content). It
        # rides on EVERY turn, not just the first: ``/agent`` can swap the agent
        # mid-conversation and a resumed session would otherwise lose it. The inbound
        # platform_message_id rides along so the turn can react on it (the
        # receipt/completion ack of "Acknowledge receipt and completion by capability")
        # where the transport supports reactions, and the sender's mention id so a group
        # reply opens by @mentioning whoever asked (see "Mention the asker in a group
        # answer").
        origin = format_origin(msg, platform=binding.channel_type)
        await self._turn_driver.submit(
            binding,
            peer,
            QueuedInbound(
                text=f"{origin}\n\n{text or attachment_note(attachments)}",
                attachments=attachments,
                thread_id=msg.thread_id,
                chat_kind=msg.chat_kind,
                reply_to_message_id=msg.platform_message_id,
                mention_user_id=msg.sender_mention_id,
                mention_user_email=msg.sender_mention_email,
                title_hint=title_hint,
            ),
        )

    async def on_callback(self, cb: InboundCallback) -> None:
        """A selection-card button tap (handled in ``inbound_events``)."""
        binding = self._bindings.get(cb.channel)
        if binding is None:
            return
        await self._events.on_callback(binding, cb)

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
        await self._events.on_stop(
            binding, event, session=self._session(event.channel, event.chat_id, event.thread_id)
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
            f"✅ Paired. This chat now controls Coffer channel "
            f"'{binding.resource.name}'.\n\n{HELP_TEXT}",
        )

    # -- helpers ---------------------------------------------------------------

    def _session(self, channel: str, chat_id: str, thread_id: str) -> _Session:
        key = (channel, chat_id, thread_id)
        if key not in self._sessions:
            self._sessions[key] = _Session()
        return self._sessions[key]
