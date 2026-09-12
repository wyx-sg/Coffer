"""The shared inbound pipeline: every channel's messages flow through here.

owner gate → pairing claim → commands → queueing → conversation mapping →
turn driving (execution lives in ``turn_driver``, rendering in ``turn_render``).

The chat platform is reached only through its public seams (conversation
service + turn orchestrator), exactly like the web UI: agents cannot tell a
channel turn from a UI turn, and a new agent provider is reachable from every
channel with no code here changing. Slash-command handling lives in
``commands``, conversation creation in ``conversation_ops``, running a
queued turn end-to-end in ``turn_driver``, and the two inbound callbacks that
never drive a turn (a card tap, a chat-lifecycle event) in ``inbound_events``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

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
    ChannelPeer,
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
    ContextFetchPort,
    ModelSuggestionPort,
)
from coffer.application.channel.turn_driver import (
    QUEUE_MAX as _QUEUE_MAX,
)
from coffer.application.channel.turn_driver import (
    ConversationPort,
    TurnDriver,
    TurnPort,
)
from coffer.application.channel.turn_driver import (
    Session as _Session,
)
from coffer.application.channel.turn_media import attachment_note
from coffer.domain.channel.envelopes import (
    InboundCallback,
    InboundLifecycle,
    InboundMessage,
    InboundStop,
)
from coffer.domain.channel.rich_content import flatten_context, format_origin
from coffer.domain.chat.attachment import Attachment

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
    ) -> None:
        self._peers = peers
        self._threads = threads
        self._pairing = pairing
        self._conversations = conversations
        self._turns = turns
        self._audit = audit
        self._bindings: dict[str, ChannelBinding] = {}
        # Keyed by (channel, chat_id, thread_id): one peer's DM, one group's
        # main chat, and each of that group's threads all drain independently.
        self._sessions: dict[tuple[str, str, str], _Session] = {}
        self._commands = ChannelCommands(
            threads=threads,
            conversations=conversations,
            turns=turns,
            agents=agents,
            model_suggestions=model_suggestions,
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
        )

    # -- runtime registry ------------------------------------------------

    def bind(self, binding: ChannelBinding) -> None:
        self._bindings[binding.name] = binding

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
            if session.drain_task is not None:
                session.drain_task.cancel()
            # Cancelling the drain task only stops the renderer; the
            # orchestrator turn keeps running and would deliver its reply to
            # the web UI alone, leaving the bot silent. Interrupt the live
            # turn so its partial reply is the contract — not a turn that
            # completes undelivered.
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
                # FR-035: a group message that @mentions another user is aimed
                # at a human — drop it silently (no reply), before the owner
                # gate, so a bot in a busy group never butts in regardless of
                # who sent it.
                return
            owner = await self._peers.owner_sender_id(binding.resource_id)
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
            peer = await self._peers.get_by_chat(binding.resource_id, msg.chat_id)
            if peer is None:
                # First @mention from the owner in this group/thread — record
                # a peer row for it so future turns (and /commands) resolve a
                # conversation scoped to this chat, not the owner's DM.
                peer = ChannelPeer(
                    resource_id=binding.resource_id,
                    chat_id=msg.chat_id,
                    display_name=msg.sender_display,
                    paired_at=datetime.now(tz=UTC),
                    active_conversation_id=None,
                    sender_id=owner,
                )
                await self._peers.upsert(peer)
        else:
            peer = await self._peers.get_by_chat(binding.resource_id, msg.chat_id)
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
        # A slash command is text-only; a caption starting with "/" alongside an
        # attachment is a normal message, not a command. Decide on the message's
        # OWN text/attachments, before any thread history is folded in (a
        # command never fetches thread context).
        is_command = text.startswith("/") and not attachments
        if (
            not is_command
            and msg.thread_id
            and msg.thread_id != msg.platform_message_id
            and binding.adapter.capabilities.supports_history_fetch
        ):
            # Ground the turn in the thread's own conversation — in a DM just as
            # much as in a group: a thread is a thread, and SeaTalk exposes a DM
            # thread endpoint too (app v3.62.1+), so ``chat_kind`` only picks
            # which one the adapter calls. What stays group-only is what is NOT
            # fetched: reading all group-MAIN chatter is undesirable and that
            # permission is not granted anyway, so only the thread a message
            # actually landed in is ever read. A message that roots a fresh
            # thread at itself (thread_id == this message's id) holds nothing
            # else yet — skip the fetch rather than echo it back into its own
            # context. Platforms with no history-fetch API (Telegram) never
            # reach here at all. The thread's own images/files download
            # alongside its text (FR-029) so a picture in the thread reaches the
            # vision agent, not a dead file link.
            fetcher = cast(ContextFetchPort, binding.adapter)
            items, thread_atts = await fetcher.fetch_thread(
                msg.chat_id, msg.thread_id, chat_kind=msg.chat_kind
            )
            ctx = flatten_context(items, title="Thread messages")
            if ctx:
                text = f"{ctx}\n\n{text}" if text else ctx
            if thread_atts:
                attachments = attachments + tuple(
                    Attachment(path=a.path, mime=a.mime, filename=a.filename) for a in thread_atts
                )
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
                self._session(binding.name, peer.chat_id, msg.thread_id),
                # FR-064: a command answer is the asker's business, not the room's.
                private_send(safe_send, target_for_command(msg, text)),
                chat_kind=msg.chat_kind,
                thread_id=msg.thread_id,
            )
            return
        session = self._session(msg.channel, peer.chat_id, msg.thread_id)
        if len(session.queue) >= _QUEUE_MAX:
            await safe_send(
                binding,
                peer.chat_id,
                "⚠️ Busy — message dropped, try again.",
                thread_id=msg.thread_id,
                chat_kind=msg.chat_kind,
            )
            return
        # A media message with no caption still needs non-blank text to persist.
        # FR-042: the turn opens with its own provenance (platform, chat kind +
        # title + id, thread, sender) so the agent knows which group/thread it is
        # answering in instead of inferring it from the bot's group list. Folded
        # in AFTER command detection (a prefixed "/help" would stop being a
        # command) and after the empty-envelope check (a header is not content).
        # It rides on EVERY turn, not just the first: ``/agent`` can swap the
        # agent mid-conversation and a resumed session would otherwise lose it.
        # The inbound platform_message_id rides along so the turn can react on it
        # (FR-036 receipt/completion ack) where the transport supports reactions,
        # and the sender's mention id so a group reply opens by @mentioning
        # whoever asked (FR-070).
        origin = format_origin(msg, platform=binding.channel_type)
        session.queue.append(
            (
                f"{origin}\n\n{text or attachment_note(attachments)}",
                attachments,
                msg.thread_id,
                msg.chat_kind,
                msg.platform_message_id,
                msg.sender_mention_id,
                msg.sender_mention_email,
            )
        )
        if session.drain_task is None or session.drain_task.done():
            session.drain_task = asyncio.create_task(
                self._turn_driver.drain(binding, peer.chat_id, msg.thread_id),
                name=f"channel-drain:{binding.name}:{peer.chat_id}:{msg.thread_id}",
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
        """The user pressed the platform's own stop control (FR-063)."""
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
            f"✅ Paired. This chat now controls Coffer channel '{binding.name}'.\n\n{HELP_TEXT}",
        )

    # -- helpers ---------------------------------------------------------------

    def _session(self, channel: str, chat_id: str, thread_id: str) -> _Session:
        key = (channel, chat_id, thread_id)
        if key not in self._sessions:
            self._sessions[key] = _Session()
        return self._sessions[key]
