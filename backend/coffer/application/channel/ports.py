"""Ports for the channel application layer.

The core is written against these Protocols; Telegram/SeaTalk adapters in
``coffer.infrastructure.channel`` satisfy them structurally. A test fake that
implements :class:`ChannelAdapter` is the recipe for any future channel:
transport in, transport out — every behavior above it is shared.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    ChoiceButton,
    InboundAttachment,
    InboundCallback,
    InboundMessage,
    SentMessage,
)
from coffer.domain.channel.rich_content import ForwardedItem


@dataclass(frozen=True)
class AdapterCallbacks:
    """What an adapter calls when the platform delivers something."""

    on_message: Callable[[InboundMessage], Awaitable[None]]
    # A selection-card button tap (ADR channel-adapter-framework). ``None`` for
    # transports/tests that never emit one; adapters skip the callback when unset.
    on_callback: Callable[[InboundCallback], Awaitable[None]] | None = None


class LiveText(Protocol):
    """A surface the core can keep updating while a turn runs (FR-037).

    One handle == one message that grows in place. ``text`` is ALWAYS the full
    accumulated snapshot, never a delta: the transport underneath may render
    the latest snapshot (SeaTalk streaming) or rewrite the message with it
    (Telegram edit), and neither can reconstruct a text from fragments.

    The handle is terminal after ``close``: a finished/failed surface is never
    reused (a SeaTalk stream id that ended is rejected by the platform), and a
    handle that gave up simply hands its text back so the ordinary send path
    delivers the reply.
    """

    async def update(self, text: str) -> None:
        """Show ``text`` (the full accumulated reply so far) on the surface.

        Best-effort and self-throttling: the caller may offer a new snapshot as
        often as it likes. A failure is swallowed and latches the handle dead —
        the turn must never break because a progress update did not land."""
        ...

    async def close(self, text: str) -> str:
        """Finish the surface with the final ``text``, returning whatever the
        caller must STILL send through the ordinary send path ("" when the
        surface delivered all of it).

        Telegram returns ``text`` unchanged — its status message is deleted and
        the final reply is sent rendered and chunked. SeaTalk finishes its
        stream with the text (that streamed message IS the reply) and returns
        only the overflow past the platform's per-stream budget."""
        ...


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

    async def send_text(
        self,
        chat_id: str,
        markdown: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
        title: str = "",
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> SentMessage:
        """Send markdown text. When ``buttons`` is given AND the transport
        ``supports_buttons``, render them as an interactive selection card;
        otherwise the text is sent plain (buttons ignored).

        ``title`` heads that card where the transport has a title element, so
        the subject is scannable without being crammed into the body's first
        line. It applies only to a card: a transport without card titles, or a
        send with no buttons, ignores it.

        ``chat_kind`` distinguishes a group ``chat_id`` from a direct one —
        transports whose group/DM APIs differ (SeaTalk) route on it; a
        transport with one unified send path (Telegram) ignores it.
        ``thread_id``, when non-empty, threads the message where the
        transport supports it; transports without thread support ignore it.
        """
        ...

    async def open_live_text(
        self, chat_id: str, *, thread_id: str = "", chat_kind: str = "direct"
    ) -> LiveText | None:
        """Open a surface the core can keep updating for this turn (FR-037), or
        ``None`` when this transport has none — the caller then falls back to
        sending the finished reply. Only called when the transport declares
        ``capabilities.supports_live_text``; the mechanism (edit vs streaming)
        is the adapter's business."""
        ...

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None: ...

    async def update_card(
        self,
        chat_id: str,
        message_id: str,
        markdown: str,
        buttons: Sequence[ChoiceButton],
        *,
        title: str = "",
        chat_kind: str = "direct",
    ) -> None:
        """Rewrite an already-delivered selection card in place.

        Called after a tap so the card reflects what the user just chose rather
        than still offering it. Only called when the transport declares
        ``capabilities.supports_card_update``; a transport without it raises.
        A failure here is cosmetic — the switch itself already happened — so the
        caller logs and moves on rather than surfacing an error."""
        ...

    async def delete_message(self, chat_id: str, message_id: str) -> None: ...

    async def send_typing(
        self, chat_id: str, *, thread_id: str = "", chat_kind: str = "direct"
    ) -> None: ...

    async def set_reaction(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Set an emoji reaction on ``message_id`` (FR-036: 👀 on receipt, ✅ on
        completion). Only called when the transport declares
        ``capabilities.supports_reactions`` — others may raise; the core never
        reaches them (SeaTalk uses its typing signal for the same receipt cue).
        Best-effort at the call site: a failed reaction never breaks the turn."""
        ...

    async def send_media(
        self,
        chat_id: str,
        path: str,
        *,
        caption: str | None = None,
        as_photo: bool = True,
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> SentMessage:
        """Upload a local file to the chat. ``as_photo`` sends it as an inline
        image; otherwise as a document. Only called when the transport declares
        ``capabilities.supports_media`` — others may raise.

        ``thread_id``/``chat_kind`` route the upload the same way ``send_text``
        does: a file returned during a group/thread turn lands in that same
        chat_kind + thread, not the group main chat."""
        ...


@dataclass(frozen=True)
class ChannelBinding:
    """A live channel the runtime has started: resource identity + adapter +
    the agent defaults the channel routes to."""

    name: str
    resource_id: int
    channel_type: str
    default_agent: str
    default_agent_config: dict[str, Any] | None
    adapter: ChannelAdapter
    # Group inbound gating (FR-035), sourced from the channel config.
    require_mention: bool = True
    ignore_other_mentions: bool = False


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
    # Sticky structural choice: which agent new conversations use.
    # ``None`` means fall back to the channel default.
    preferred_agent: str | None = None


class ChannelPeerRepoPort(Protocol):
    """Persistence for peer bindings."""

    async def get(self, resource_id: int) -> ChannelPeer | None: ...

    async def get_by_chat(self, resource_id: int, chat_id: str) -> ChannelPeer | None: ...

    async def list_by_resource(self, resource_id: int) -> list[ChannelPeer]: ...

    async def owner_sender_id(self, resource_id: int) -> str | None:
        """The first non-null ``sender_id`` paired for this channel, across
        all its peer rows (DM + any groups/threads). ``None`` when the
        channel has no peer with a known sender identity."""
        ...

    async def upsert(self, peer: ChannelPeer) -> None: ...

    async def set_active_conversation(
        self, resource_id: int, chat_id: str, conversation_id: str | None
    ) -> None: ...

    async def set_preferences(
        self,
        resource_id: int,
        *,
        preferred_agent: str | None,
    ) -> None: ...


@dataclass(frozen=True)
class ChannelThreadConversation:
    """The per-thread conversation binding (one row in
    ``channel_thread_conversations``): conversation identity is keyed by
    ``(resource_id, chat_id, thread_id)`` (FR-032), not by the peer alone.

    ``thread_id=""`` is the DM (or a group's main chat); each thread in a group
    is an independent row with its own active conversation and its own sticky
    agent. Pairing/owner identity stays on ``ChannelPeer`` — this binding only
    owns the conversation a turn drives and the agent it opens with."""

    resource_id: int
    chat_id: str
    thread_id: str
    active_conversation_id: str | None
    # Sticky structural choice for THIS thread: which agent new conversations
    # use. ``None`` means fall back to the channel default.
    preferred_agent: str | None
    updated_at: datetime


class ChannelThreadConversationRepoPort(Protocol):
    """Persistence for per-thread conversation bindings (FR-032).

    The source of truth for driving a turn: which conversation a
    ``(resource_id, chat_id, thread_id)`` resolves to, and the sticky agent it
    opens with. Two threads of one group therefore never collide on a single
    conversation (the "a turn is already running" error)."""

    async def get(
        self, resource_id: int, chat_id: str, thread_id: str
    ) -> ChannelThreadConversation | None: ...

    async def set_active_conversation(
        self, resource_id: int, chat_id: str, thread_id: str, conversation_id: str | None
    ) -> None:
        """Upsert the thread's active conversation, leaving ``preferred_agent``
        untouched (creating the row if this thread has none yet)."""
        ...

    async def set_preferred_agent(
        self, resource_id: int, chat_id: str, thread_id: str, preferred_agent: str | None
    ) -> None:
        """Upsert the thread's sticky agent, leaving ``active_conversation_id``
        untouched (creating the row if this thread has none yet)."""
        ...


class AgentCatalogPort(Protocol):
    """The slice of the agent registry the channel core needs to route by key:
    list the available agents and validate a chosen key. Satisfied structurally
    by ``AgentProviderRegistry``."""

    def agent_keys(self) -> list[str]: ...

    # ``(agent_key, display_name)`` pairs for rendering a selection card.
    def agent_choices(self) -> list[tuple[str, str]]: ...


class ModelSuggestionPort(Protocol):
    """Best-effort model quick-picks for a managed agent's ``/model`` selection
    card: the active provider profile's ``model`` (and ``fast_model``) for the
    agent's wire (ADR provider-switching), mirroring the web model picker. Empty when there is
    no active profile — the card then offers only the free-text path."""

    async def suggest(self, agent_key: str) -> list[str]: ...


class ContextFetchPort(Protocol):
    """Best-effort thread-context reader for a group @mention: when the
    @mention landed inside a thread, the thread's own messages ground the
    turn. Group-main @mentions fetch nothing (reading all group chatter is
    undesirable — the group-chat-history permission is intentionally not
    granted). Platforms without a history-fetch API (Telegram's Bot API)
    satisfy this by always returning ``([], ())``."""

    async def fetch_thread(
        self, chat_id: str, thread_id: str, *, limit: int = 50
    ) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
        """Return the thread's ``(text items, downloaded attachments)``: the
        flattened text of each thread message plus the images/files those
        messages carry, already fetched to local paths (FR-029) so an in-thread
        @mention reaches the turn with the real pictures, not dead file links.
        Degrades to ``([], ())`` on any error."""
        ...


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


class TunnelControllerPort(Protocol):
    """Lifecycle of per-channel cloudflared named-tunnel child processes.

    One process per managed channel (each named tunnel has its own connector
    token). ``ensure_running`` is idempotent and respawns when the token
    changes; ``active`` reports which channels currently have a live tunnel so
    the reconciler can stop the ones no longer desired.
    """

    def running(self, name: str) -> bool: ...

    def active(self) -> set[str]: ...

    async def ensure_running(self, name: str, token: str) -> None: ...

    async def ensure_stopped(self, name: str) -> None: ...

    async def dispose(self) -> None: ...
