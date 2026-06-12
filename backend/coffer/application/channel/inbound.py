"""The shared inbound pipeline: every channel's messages flow through here.

owner gate → pairing claim → commands → queueing → conversation mapping →
turn driving (rendering lives in ``turn_render``) → approval bridging.

The chat platform is reached only through its public seams (conversation
service + turn orchestrator), exactly like the web UI: agents cannot tell a
channel turn from a UI turn, and a new agent provider is reachable from every
channel with no code here changing.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from coffer.application.audit_service import AuditService
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import (
    ChannelAdapter,
    ChannelPeer,
    ChannelPeerRepoPort,
)
from coffer.application.channel.turn_render import PendingApproval, TurnRenderer
from coffer.application.chat.ports import ApprovalDecision
from coffer.domain.audit import AuditEventType
from coffer.domain.channel.envelopes import (
    ApprovalClick,
    InboundMessage,
    parse_approval_value,
)
from coffer.domain.chat.errors import ApprovalNotFound, ConversationNotFound, TurnInProgress
from coffer.domain.errors import CofferError
from coffer.domain.resource import ResourceRef

_logger = logging.getLogger(__name__)

_QUEUE_MAX = 10

_HELP_TEXT = (
    "Coffer channel commands:\n"
    "/new — start a fresh conversation\n"
    "/stop — interrupt the running turn\n"
    "/status — active conversation and turn state\n"
    "/help — this list"
)


class ConversationPort(Protocol):
    """The slice of the chat platform's conversation service we use."""

    async def create_conversation(
        self, *, agent_key: str, agent_config: dict[str, Any] | None, actor: str
    ) -> Any: ...

    async def get_conversation(self, conversation_id: str) -> Any: ...


class TurnPort(Protocol):
    """The slice of the turn orchestrator we use."""

    async def start_turn(self, conversation_id: str, user_text: str) -> asyncio.Queue[Any]: ...

    def interrupt_turn(self, conversation_id: str) -> None: ...

    def submit_approval(
        self, conversation_id: str, request_id: str, decision: ApprovalDecision
    ) -> None: ...


@dataclass(frozen=True)
class ChannelBinding:
    """A live channel the runtime has started: resource identity + adapter."""

    name: str
    resource_id: int
    channel_type: str
    default_agent: str
    default_agent_config: dict[str, Any] | None
    adapter: ChannelAdapter


@dataclass
class _Session:
    queue: deque[str] = field(default_factory=lambda: deque(maxlen=_QUEUE_MAX))
    drain_task: asyncio.Task[None] | None = None
    pending_approvals: dict[str, PendingApproval] = field(default_factory=dict)
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
    ) -> None:
        self._peers = peers
        self._pairing = pairing
        self._conversations = conversations
        self._turns = turns
        self._audit = audit
        self._bindings: dict[str, ChannelBinding] = {}
        self._sessions: dict[str, _Session] = {}

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
        # A turn parked on an approval gate would wait forever once its
        # prompt's buttons are gone — interrupt it instead of wedging the
        # conversation until a manual /stop.
        for pending in session.pending_approvals.values():
            with contextlib.suppress(Exception):
                self._turns.interrupt_turn(pending.conversation_id)
        session.pending_approvals.clear()

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
        text = msg.text.strip()
        if not text:
            # Non-text content reaches the core as an empty envelope.
            await self._safe_send(
                binding, peer.chat_id, "⚠️ Only text messages are supported for now."
            )
            return
        if text.startswith("/"):
            await self._handle_command(binding, peer, text)
            return
        session = self._session(msg.channel)
        if len(session.queue) >= _QUEUE_MAX:
            await self._safe_send(binding, peer.chat_id, "⚠️ Busy — message dropped, try again.")
            return
        session.queue.append(text)
        if session.drain_task is None or session.drain_task.done():
            session.drain_task = asyncio.create_task(
                self._drain(binding), name=f"channel-drain:{binding.name}"
            )

    async def on_approval_click(self, click: ApprovalClick) -> None:
        binding = self._bindings.get(click.channel)
        if binding is None:
            return
        peer = await self._peers.get(binding.resource_id)
        if peer is None or peer.chat_id != click.chat_id:
            return  # only the owner decides
        parsed = parse_approval_value(click.value)
        if parsed is None:
            return
        request_id, decision_word = parsed
        session = self._session(click.channel)
        pending = session.pending_approvals.pop(request_id, None)
        if pending is None:
            return
        outcome = "✅ Approved" if decision_word == "allow" else "❌ Denied"
        decision: Literal["allow", "deny"] = "allow" if decision_word == "allow" else "deny"
        try:
            self._turns.submit_approval(
                pending.conversation_id,
                request_id,
                ApprovalDecision(behavior=decision),
            )
        except ApprovalNotFound:
            outcome = "⌛ Expired"
        with contextlib.suppress(Exception):
            await binding.adapter.resolve_approval_prompt(
                pending.chat_id, pending.message_id, outcome
            )

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
            f"✅ Paired. This chat now controls Coffer channel '{binding.name}'.\n\n{_HELP_TEXT}",
        )

    # -- commands ------------------------------------------------------------

    async def _handle_command(self, binding: ChannelBinding, peer: ChannelPeer, text: str) -> None:
        command = text.split()[0].lower()
        if command in ("/help", "/start"):
            await self._safe_send(binding, peer.chat_id, _HELP_TEXT)
        elif command == "/new":
            try:
                conv = await self._conversations.create_conversation(
                    agent_key=binding.default_agent,
                    agent_config=binding.default_agent_config,
                    actor="channel",
                )
            except CofferError as e:
                await self._safe_send(binding, peer.chat_id, f"⚠️ {e} [{e.code}]")
                return
            await self._peers.set_active_conversation(binding.resource_id, conv.id)
            await self._safe_send(binding, peer.chat_id, "🆕 Started a fresh conversation.")
        elif command == "/stop":
            # The turn that is actually draining wins over the peer's bound
            # conversation: after ``/new`` rebinds the peer, a turn can still be
            # running on the previous conversation. Stopping the bound (idle)
            # conversation would claim "Stopping…" while the real turn runs on.
            session = self._session(binding.name)
            target = session.running_conversation_id or peer.active_conversation_id
            if target is not None:
                self._turns.interrupt_turn(target)
                await self._safe_send(binding, peer.chat_id, "⏹ Stopping…")
            else:
                await self._safe_send(binding, peer.chat_id, "Nothing is running.")
        elif command == "/status":
            session = self._session(binding.name)
            running = session.drain_task is not None and not session.drain_task.done()
            conv = peer.active_conversation_id or "none yet"
            await self._safe_send(
                binding,
                peer.chat_id,
                f"Conversation: {conv}\nAgent: {binding.default_agent}\n"
                f"Turn running: {'yes' if running else 'no'}\nQueued: {len(session.queue)}",
            )
        else:
            await self._safe_send(binding, peer.chat_id, f"Unknown command {command}. /help")

    # -- turn driving ----------------------------------------------------------

    async def _drain(self, binding: ChannelBinding) -> None:
        session = self._session(binding.name)
        while session.queue:
            text = session.queue.popleft()
            peer = await self._peers.get(binding.resource_id)
            if peer is None:
                break
            try:
                await self._run_turn(binding, peer, text)
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("channel.turn.failed", extra={"channel": binding.name})

    async def _ensure_conversation(self, binding: ChannelBinding, peer: ChannelPeer) -> str:
        if peer.active_conversation_id is not None:
            try:
                await self._conversations.get_conversation(peer.active_conversation_id)
            except ConversationNotFound:
                pass
            else:
                return peer.active_conversation_id
        conv = await self._conversations.create_conversation(
            agent_key=binding.default_agent,
            agent_config=binding.default_agent_config,
            actor="channel",
        )
        await self._peers.set_active_conversation(binding.resource_id, conv.id)
        return str(conv.id)

    async def _run_turn(self, binding: ChannelBinding, peer: ChannelPeer, text: str) -> None:
        adapter = binding.adapter
        try:
            conversation_id = await self._ensure_conversation(binding, peer)
        except CofferError as e:
            # e.g. the channel's default agent is unknown/misconfigured — the
            # owner must see it in the chat, not only in the daemon log.
            await self._safe_send(binding, peer.chat_id, f"⚠️ {e} [{e.code}]")
            return
        if adapter.capabilities.supports_typing:
            with contextlib.suppress(Exception):
                await adapter.send_typing(peer.chat_id)
        try:
            queue = await self._turns.start_turn(conversation_id, text)
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
            pending_approvals=session.pending_approvals,
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

    async def _safe_send(self, binding: ChannelBinding, chat_id: str, text: str) -> None:
        try:
            await binding.adapter.send_text(chat_id, text)
        except Exception:
            _logger.exception("channel.send.failed", extra={"channel": binding.name})
