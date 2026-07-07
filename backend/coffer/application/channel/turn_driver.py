"""Turn execution: driving one queued inbound turn through the chat platform.

Split out of ``InboundProcessor`` (Task 8.5, behavior-preserving) to keep
that module under the file-size limit. ``TurnDriver`` owns the turn
lifecycle only — ensure-conversation, audit, typing, ``start_turn``,
rendering the reply — plus the drain loop that feeds it from a session's
queue. Owner-gating, pairing, command dispatch, and the session/queue
registry itself stay in ``inbound``.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from coffer.application.audit_service import AuditService
from coffer.application.channel.conversation_ops import (
    ensure_conversation,
    explain_conversation_error,
)
from coffer.application.channel.ports import ChannelBinding, ChannelPeer, ChannelPeerRepoPort
from coffer.application.channel.turn_render import TurnRenderer
from coffer.domain.audit import AuditEventType
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.errors import TurnInProgress
from coffer.domain.errors import CofferError
from coffer.domain.resource import ResourceRef

__all__ = ["QUEUE_MAX", "ConversationPort", "Session", "TurnDriver", "TurnPort"]

_logger = logging.getLogger(__name__)

QUEUE_MAX = 10

#: One queued inbound turn: the text to drive it, any downloaded attachments to
#: materialise for the agent (images inlined, files handed off by path), the
#: thread the message arrived in (empty for a threadless chat), and the chat
#: kind ("direct" | "group") so the eventual reply is routed back to the same
#: place the message came from.
_QueuedInbound = tuple[str, tuple[Attachment, ...], str, str]

#: Sends one reply back through a channel binding, matching
#: ``InboundProcessor._safe_send``'s signature (buttons omitted — turn
#: driving never sends a selection card).
SafeSend = Callable[..., Awaitable[None]]

#: Looks up (creating if absent) the session keyed by (channel, chat_id,
#: thread_id) — the same registry ``InboundProcessor`` uses for queueing.
SessionAccessor = Callable[[str, str, str], "Session"]


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
class Session:
    queue: deque[_QueuedInbound] = field(default_factory=lambda: deque(maxlen=QUEUE_MAX))
    drain_task: asyncio.Task[None] | None = None
    # The conversation whose turn is draining right now (None between turns).
    # Tracked separately from the peer's active conversation: ``/new`` rebinds
    # the peer while a turn keeps draining on the old conversation, so ``/stop``
    # and unbind must target the turn that is actually running.
    running_conversation_id: str | None = None


class TurnDriver:
    """Drains one session's queue and runs each item as a chat-platform turn."""

    def __init__(
        self,
        *,
        peers: ChannelPeerRepoPort,
        conversations: ConversationPort,
        turns: TurnPort,
        audit: AuditService,
        safe_send: SafeSend,
        session: SessionAccessor,
    ) -> None:
        self._peers = peers
        self._conversations = conversations
        self._turns = turns
        self._audit = audit
        self._safe_send = safe_send
        self._session = session

    async def drain(self, binding: ChannelBinding, chat_id: str, thread_id: str) -> None:
        session = self._session(binding.name, chat_id, thread_id)
        while session.queue:
            user_text, attachments, item_thread_id, chat_kind = session.queue.popleft()
            peer = await self._peers.get_by_chat(binding.resource_id, chat_id)
            if peer is None:
                break
            try:
                await self.run_turn(
                    binding,
                    peer,
                    user_text,
                    attachments,
                    thread_id=item_thread_id,
                    chat_kind=chat_kind,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("channel.turn.failed", extra={"channel": binding.name})

    async def run_turn(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        text: str,
        attachments: Sequence[Attachment] = (),
        *,
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> None:
        adapter = binding.adapter
        try:
            conversation_id = await ensure_conversation(
                self._conversations, self._peers, binding, peer
            )
        except CofferError as e:
            # e.g. the channel's default agent is unknown/misconfigured — the
            # owner must see it in the chat, not only in the daemon log.
            await self._safe_send(
                binding,
                peer.chat_id,
                explain_conversation_error(e),
                thread_id=thread_id,
                chat_kind=chat_kind,
            )
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
                binding,
                peer.chat_id,
                "⚠️ A turn is already running for this conversation.",
                thread_id=thread_id,
                chat_kind=chat_kind,
            )
            return
        except CofferError as e:
            await self._safe_send(
                binding,
                peer.chat_id,
                f"⚠️ {e} [{e.code}]",
                thread_id=thread_id,
                chat_kind=chat_kind,
            )
            return
        session = self._session(binding.name, peer.chat_id, thread_id)

        async def _send(message: str) -> None:
            await self._safe_send(
                binding, peer.chat_id, message, thread_id=thread_id, chat_kind=chat_kind
            )

        renderer = TurnRenderer(
            channel=binding.name,
            adapter=adapter,
            chat_id=peer.chat_id,
            conversation_id=conversation_id,
            send=_send,
            thread_id=thread_id,
            chat_kind=chat_kind,
        )
        # Track the live turn so /stop and unbind can target it even after /new
        # rebinds the peer to a fresh conversation mid-turn.
        session.running_conversation_id = conversation_id
        try:
            await renderer.consume(queue)
        finally:
            if session.running_conversation_id == conversation_id:
                session.running_conversation_id = None
