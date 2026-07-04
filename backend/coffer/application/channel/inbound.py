"""The shared inbound pipeline: every channel's messages flow through here.

owner gate → pairing claim → commands → queueing → conversation mapping →
turn driving (rendering lives in ``turn_render``).

The chat platform is reached only through its public seams (conversation
service + turn orchestrator), exactly like the web UI: agents cannot tell a
channel turn from a UI turn, and a new agent provider is reachable from every
channel with no code here changing. Slash-command handling lives in
``commands`` and conversation creation in ``conversation_ops``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from coffer.application.audit_service import AuditService
from coffer.application.channel.commands import HELP_TEXT, ChannelCommands
from coffer.application.channel.conversation_ops import (
    ensure_conversation,
    explain_conversation_error,
)
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import (
    AgentCatalogPort,
    ChannelBinding,
    ChannelPeer,
    ChannelPeerRepoPort,
    ModelSuggestionPort,
)
from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.audit import AuditEventType
from coffer.domain.channel.envelopes import ChoiceButton, InboundCallback, InboundMessage
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.errors import TurnInProgress
from coffer.domain.errors import CofferError
from coffer.domain.resource import ResourceRef

__all__ = ["ChannelBinding", "InboundProcessor"]

_logger = logging.getLogger(__name__)

_QUEUE_MAX = 10

#: One queued inbound turn: the text to drive it, and any downloaded attachments
#: to materialise for the agent (images inlined, files handed off by path).
_QueuedInbound = tuple[str, tuple[Attachment, ...]]


def _attachment_note(attachments: Sequence[Attachment]) -> str:
    """A short stand-in text for a media message with no caption, so the persisted
    user turn is not blank (the bytes reach the agent out-of-band)."""
    names = ", ".join(a.filename for a in attachments)
    kind = "image" if all(a.is_image for a in attachments) else "file"
    plural = "s" if len(attachments) != 1 else ""
    return f"(sent {len(attachments)} {kind}{plural}: {names})"


class ConversationPort(Protocol):
    """The slice of the chat platform's conversation service we use."""

    async def create_conversation(
        self,
        *,
        agent_key: str,
        agent_config: dict[str, Any] | None,
        actor: str,
        channel_name: str | None = None,
        peer_chat_id: str | None = None,
    ) -> Any: ...

    async def get_conversation(self, conversation_id: str) -> Any: ...

    async def set_conversation_model(
        self, conversation_id: str, *, model_id: str | None
    ) -> Any: ...

    async def get_agent_config(self, conversation_id: str) -> AgentConfig: ...

    async def set_agent_config(self, conversation_id: str, config: AgentConfig) -> None: ...


class TurnPort(Protocol):
    """The slice of the turn orchestrator we use."""

    async def start_turn(
        self,
        conversation_id: str,
        user_text: str,
        *,
        attachments: Sequence[Attachment] = (),
    ) -> asyncio.Queue[Any]: ...

    def interrupt_turn(self, conversation_id: str) -> None: ...


@dataclass
class _Session:
    queue: deque[_QueuedInbound] = field(default_factory=lambda: deque(maxlen=_QUEUE_MAX))
    drain_task: asyncio.Task[None] | None = None
    # The conversation whose turn is draining right now (None between turns).
    # Tracked separately from the peer's active conversation: ``/new`` rebinds
    # the peer while a turn keeps draining on the old conversation, so ``/stop``
    # and unbind must target the turn that is actually running.
    running_conversation_id: str | None = None


class InboundProcessor:
    """Owner-gated bridge from adapter callbacks to chat-platform turns."""

    def __init__(
        self,
        *,
        peers: ChannelPeerRepoPort,
        pairing: PairingManager,
        conversations: ConversationPort,
        turns: TurnPort,
        audit: AuditService,
        agents: AgentCatalogPort,
        model_suggestions: ModelSuggestionPort,
    ) -> None:
        self._peers = peers
        self._pairing = pairing
        self._conversations = conversations
        self._turns = turns
        self._audit = audit
        self._bindings: dict[str, ChannelBinding] = {}
        self._sessions: dict[str, _Session] = {}
        self._commands = ChannelCommands(
            peers=peers,
            conversations=conversations,
            turns=turns,
            agents=agents,
            model_suggestions=model_suggestions,
        )

    # -- runtime registry ------------------------------------------------

    def bind(self, binding: ChannelBinding) -> None:
        self._bindings[binding.name] = binding

    def unbind(self, name: str) -> None:
        self._bindings.pop(name, None)
        session = self._sessions.pop(name, None)
        if session is None:
            return
        if session.drain_task is not None:
            session.drain_task.cancel()
        # Cancelling the drain task only stops the renderer; the orchestrator
        # turn keeps running and would deliver its reply to the web UI alone,
        # leaving the bot silent. Interrupt the live turn so its partial reply
        # is the contract — not a turn that completes undelivered.
        if session.running_conversation_id is not None:
            with contextlib.suppress(Exception):
                self._turns.interrupt_turn(session.running_conversation_id)
            session.running_conversation_id = None

    def binding(self, name: str) -> ChannelBinding | None:
        return self._bindings.get(name)

    def shutdown(self) -> None:
        for name in list(self._sessions):
            self.unbind(name)
        self._bindings.clear()

    # -- adapter callbacks -------------------------------------------------

    async def on_message(self, msg: InboundMessage) -> None:
        binding = self._bindings.get(msg.channel)
        if binding is None:
            return
        peer = await self._peers.get(binding.resource_id)
        if peer is None or peer.chat_id != msg.chat_id:
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
        if not text and not attachments:
            # An empty envelope with nothing downloadable (a sticker, a location,
            # a media type the transport does not extract).
            await self._safe_send(
                binding, peer.chat_id, "⚠️ Unsupported message — send text, a photo, or a file."
            )
            return
        # A slash command is text-only; a caption starting with "/" alongside an
        # attachment is a normal message, not a command.
        if text.startswith("/") and not attachments:
            await self._commands.handle(
                binding, peer, text, self._session(binding.name), self._safe_send
            )
            return
        session = self._session(msg.channel)
        if len(session.queue) >= _QUEUE_MAX:
            await self._safe_send(binding, peer.chat_id, "⚠️ Busy — message dropped, try again.")
            return
        # A media message with no caption still needs non-blank text to persist.
        session.queue.append((text or _attachment_note(attachments), attachments))
        if session.drain_task is None or session.drain_task.done():
            session.drain_task = asyncio.create_task(
                self._drain(binding), name=f"channel-drain:{binding.name}"
            )

    async def on_callback(self, cb: InboundCallback) -> None:
        """A selection-card button tap. Owner-gated exactly like ``on_message``
        (an intruder in a paired group must not flip the owner's agent/model by
        tapping), then routed to the same switch the text command performs. A
        tap never pairs — an unpaired/foreign chat is ignored silently."""
        binding = self._bindings.get(cb.channel)
        if binding is None:
            return
        peer = await self._peers.get(binding.resource_id)
        if peer is None or peer.chat_id != cb.chat_id:
            return
        if peer.sender_id is not None and cb.sender_id and peer.sender_id != cb.sender_id:
            return
        await self._commands.dispatch_callback(binding, peer, cb.data, self._safe_send)

    # -- pairing -----------------------------------------------------------

    async def _maybe_pair(self, binding: ChannelBinding, msg: InboundMessage) -> None:
        # Non-text content arrives as an empty envelope; never let it burn a
        # pairing attempt (a stranger's sticker must not invalidate the code).
        if not msg.text.strip():
            return
        if not self._pairing.try_claim(binding.name, msg.text):
            _logger.debug("channel.inbound.ignored", extra={"channel": binding.name})
            return
        peer = ChannelPeer(
            resource_id=binding.resource_id,
            chat_id=msg.chat_id,
            display_name=msg.sender_display,
            paired_at=datetime.now(tz=UTC),
            active_conversation_id=None,
            sender_id=msg.sender_id or None,
        )
        await self._peers.upsert(peer)
        await self._audit.record(
            AuditEventType.CHANNEL_PAIRED.value,
            ref=ResourceRef(kind="channel", name=binding.name),
            actor="channel",
            details={"chat_id": msg.chat_id, "display_name": msg.sender_display},
        )
        await self._safe_send(
            binding,
            msg.chat_id,
            f"✅ Paired. This chat now controls Coffer channel '{binding.name}'.\n\n{HELP_TEXT}",
        )

    # -- turn driving ----------------------------------------------------------

    async def _drain(self, binding: ChannelBinding) -> None:
        session = self._session(binding.name)
        while session.queue:
            user_text, attachments = session.queue.popleft()
            peer = await self._peers.get(binding.resource_id)
            if peer is None:
                break
            try:
                await self._run_turn(binding, peer, user_text, attachments)
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("channel.turn.failed", extra={"channel": binding.name})

    async def _run_turn(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        text: str,
        attachments: Sequence[Attachment] = (),
    ) -> None:
        adapter = binding.adapter
        try:
            conversation_id = await ensure_conversation(
                self._conversations, self._peers, binding, peer
            )
        except CofferError as e:
            # e.g. the channel's default agent is unknown/misconfigured — the
            # owner must see it in the chat, not only in the daemon log.
            await self._safe_send(binding, peer.chat_id, explain_conversation_error(e))
            return
        # A channel message driving a turn is first-class in the audit log:
        # who (the peer), through which channel, drives which agent.
        with contextlib.suppress(Exception):
            conv = await self._conversations.get_conversation(conversation_id)
            await self._audit.record(
                AuditEventType.CHANNEL_TURN_STARTED.value,
                ref=ResourceRef(kind="channel", name=binding.name),
                actor=peer.display_name or "channel",
                details={
                    "channel": binding.name,
                    "chat_id": peer.chat_id,
                    "display_name": peer.display_name,
                    "agent_key": conv.agent_key,
                    "conversation_id": conversation_id,
                },
            )
        if adapter.capabilities.supports_typing:
            with contextlib.suppress(Exception):
                await adapter.send_typing(peer.chat_id)
        try:
            queue = await self._turns.start_turn(conversation_id, text, attachments=attachments)
        except TurnInProgress:
            await self._safe_send(
                binding, peer.chat_id, "⚠️ A turn is already running for this conversation."
            )
            return
        except CofferError as e:
            await self._safe_send(binding, peer.chat_id, f"⚠️ {e} [{e.code}]")
            return
        session = self._session(binding.name)

        async def _send(message: str) -> None:
            await self._safe_send(binding, peer.chat_id, message)

        renderer = TurnRenderer(
            channel=binding.name,
            adapter=adapter,
            chat_id=peer.chat_id,
            conversation_id=conversation_id,
            send=_send,
        )
        # Track the live turn so /stop and unbind can target it even after /new
        # rebinds the peer to a fresh conversation mid-turn.
        session.running_conversation_id = conversation_id
        try:
            await renderer.consume(queue)
        finally:
            if session.running_conversation_id == conversation_id:
                session.running_conversation_id = None

    # -- helpers ---------------------------------------------------------------

    def _session(self, name: str) -> _Session:
        if name not in self._sessions:
            self._sessions[name] = _Session()
        return self._sessions[name]

    async def _safe_send(
        self,
        binding: ChannelBinding,
        chat_id: str,
        text: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
    ) -> None:
        try:
            await binding.adapter.send_text(chat_id, text, buttons=buttons)
        except Exception:
            _logger.exception("channel.send.failed", extra={"channel": binding.name})
