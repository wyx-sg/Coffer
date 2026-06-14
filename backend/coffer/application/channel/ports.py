"""Ports for the channel application layer.

The core is written against these Protocols; Telegram/SeaTalk adapters in
``coffer.infrastructure.channel`` satisfy them structurally. A test fake that
implements :class:`ChannelAdapter` is the recipe for any future channel:
transport in, transport out — every behavior above it is shared.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from coffer.domain.channel.envelopes import (
    ApprovalClick,
    ChannelCapabilities,
    InboundMessage,
    SentMessage,
)


@dataclass(frozen=True)
class AdapterCallbacks:
    """What an adapter calls when the platform delivers something."""

    on_message: Callable[[InboundMessage], Awaitable[None]]
    on_approval_click: Callable[[ApprovalClick], Awaitable[None]]


class ChannelAdapter(Protocol):
    """One live transport binding for one channel resource.

    ``start`` begins inbound delivery (spawning internal tasks as needed) and
    returns; ``stop`` halts everything. Outbound methods accept markdown text
    and own the platform rendering + chunking. Methods the transport cannot
    honour (see ``capabilities``) may raise; the core never calls them.
    """

    @property
    def capabilities(self) -> ChannelCapabilities: ...

    async def start(self, callbacks: AdapterCallbacks) -> None: ...

    async def stop(self) -> None: ...

    async def send_text(self, chat_id: str, markdown: str) -> SentMessage: ...

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None: ...

    async def delete_message(self, chat_id: str, message_id: str) -> None: ...

    async def send_typing(self, chat_id: str) -> None: ...

    async def send_approval_prompt(
        self, chat_id: str, text: str, *, allow_value: str, deny_value: str
    ) -> SentMessage: ...

    async def resolve_approval_prompt(
        self, chat_id: str, message_id: str, outcome_text: str
    ) -> None: ...


@dataclass(frozen=True)
class ChannelPeer:
    """The paired owner of a channel (one row in channel_peers)."""

    resource_id: int
    chat_id: str
    display_name: str
    paired_at: datetime
    active_conversation_id: str | None
    # The paired sender's stable identity (Telegram from.id, SeaTalk
    # employee_code); the owner gate checks it when present. ``None`` on rows
    # paired before the gate gained sender awareness → chat-id-only fallback.
    sender_id: str | None = None
    # Sticky structural choices: which agent and which channel workspace new
    # conversations use. ``None`` means fall back to the channel defaults.
    preferred_agent: str | None = None
    preferred_workspace: str | None = None


class ChannelPeerRepoPort(Protocol):
    """Persistence for peer bindings."""

    async def get(self, resource_id: int) -> ChannelPeer | None: ...

    async def upsert(self, peer: ChannelPeer) -> None: ...

    async def set_active_conversation(
        self, resource_id: int, conversation_id: str | None
    ) -> None: ...

    async def set_preferences(
        self,
        resource_id: int,
        *,
        preferred_agent: str | None,
        preferred_workspace: str | None,
    ) -> None: ...


@runtime_checkable
class EventIngestAdapter(Protocol):
    """An adapter that receives platform events pushed from outside the
    daemon (the callback listener) instead of polling for them."""

    async def handle_event(self, envelope: dict[str, Any]) -> None: ...


class ListenerControllerPort(Protocol):
    """Lifecycle of the callback-listener child process."""

    @property
    def port(self) -> int: ...

    def running(self) -> bool: ...

    async def ensure_running(self, signing_secrets: dict[str, str]) -> None: ...

    async def ensure_stopped(self) -> None: ...
