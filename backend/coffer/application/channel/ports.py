"""Ports for the channel application layer.

The core is written against these Protocols; Telegram/SeaTalk adapters in
``coffer.infrastructure.channel`` satisfy them structurally. A test fake that
implements :class:`ChannelAdapter` is the recipe for any future channel:
transport in, transport out — every behavior above it is shared.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    ChoiceButton,
    EphemeralTarget,
    InboundAttachment,
    InboundCallback,
    InboundLifecycle,
    InboundMessage,
    InboundStop,
    SentMessage,
)
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

#: What a context read returns: the flattened text of each message read, and the
#: images/files those messages carry, already downloaded to local paths.
FetchedContext = tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]


@dataclass(frozen=True)
class AdapterCallbacks:
    """What an adapter calls when the platform delivers something."""

    on_message: Callable[[InboundMessage], Awaitable[None]]
    # A selection-card button tap (ADR channel-adapter-framework). ``None`` for
    # transports/tests that never emit one; adapters skip the callback when unset.
    on_callback: Callable[[InboundCallback], Awaitable[None]] | None = None
    # A non-message event about the bot's own standing in a chat (removed from a group,
    # group turned external), and the platform's own stop control being pressed (see
    # "Stop the turn from the platform's own stop control"). Both optional exactly like
    # ``on_callback``: transports and test fakes that never emit one leave it unset, and
    # adapters skip the call when it is ``None``.
    on_lifecycle: Callable[[InboundLifecycle], Awaitable[None]] | None = None
    on_stop: Callable[[InboundStop], Awaitable[None]] | None = None


class LiveText(Protocol):
    """A surface the core can keep updating while a turn runs (see "Grow a reply in
    place on one live surface").

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
        reply_to_message_id: str = "",
        ephemeral: EphemeralTarget | None = None,
    ) -> SentMessage:
        """Send markdown text. When ``buttons`` is given AND the transport
        ``supports_buttons``, render them as an interactive selection card;
        otherwise the text is sent plain (buttons ignored).

        ``title`` heads that card where the transport has a title element, so
        the subject is scannable without being crammed into the body's first
        line. It applies only to a card: a transport without card titles, or a
        send with no buttons, ignores it.

        The four routing arguments are all requests a transport may ignore when its
        platform has no such primitive: ``chat_kind`` distinguishes a group ``chat_id``
        from a direct one (SeaTalk's group/DM APIs differ; Telegram has one path),
        ``thread_id`` threads the message, ``reply_to_message_id`` attaches it as a
        platform-level reply so a busy group can tell which question an answer belongs
        to (see "Attach a group reply to the message it answers"), and ``ephemeral``
        asks for it to be shown only to that member (see "Keep non-answer chatter
        private in a group") — never a guarantee, since a platform that refuses delivers
        an ordinary message instead.
        """
        ...

    async def open_live_text(
        self, chat_id: str, *, thread_id: str = "", chat_kind: str = "direct"
    ) -> LiveText | None:
        """Open a surface the core can keep updating for this turn (see "Grow a reply in
        place on one live surface"), or ``None`` when this transport has none — the
        caller then falls back to sending the finished reply. Only called when the
        transport declares ``capabilities.supports_live_text``; the mechanism (edit vs
        streaming) is the adapter's business."""
        ...

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

    async def withdraw_message(
        self, chat_id: str, message_id: str, *, chat_kind: str = "direct"
    ) -> None:
        """Take one of the bot's own messages back (spec channels "Withdraw a bot
        reply on the owner's command"): Telegram deletes it, SeaTalk — which has no
        delete — rewrites the card into a neutral "Withdrawn" card without buttons.
        Only called inside ``capabilities.withdraw_window_hours``; a transport with
        a window of 0 raises. Raises when the platform refuses, so the caller can
        tell the owner."""
        ...

    async def send_typing(
        self,
        chat_id: str,
        *,
        thread_id: str = "",
        chat_kind: str = "direct",
        action: str = "typing",
    ) -> None:
        """Show that the bot is busy; ``action`` names what with ("upload_photo"
        / "upload_document") where the transport distinguishes."""
        ...

    async def set_reaction(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Set an emoji reaction on ``message_id`` ("Acknowledge receipt and completion
        by capability": one of ``capabilities.reactions``). Only called when the transport
        declares ``capabilities.supports_reactions`` — others may raise; the core never
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

    async def open_thread(
        self, chat_id: str, mark: str, body: str, *, anchor_message_id: str = ""
    ) -> str:
        """Open a new thread in direct chat ``chat_id`` for a parallel conversation
        and return its thread id (see "Open parallel conversations in a direct
        chat"). ``mark`` (``🧵#N title``) heads the thread — its root message, or
        its topic's name — and ``body`` follows it. How a thread is created is the
        transport's own fact. ``anchor_message_id`` is the owner's own ``/thread``
        message, given only where a direct-chat thread hangs from a message
        (``capabilities.direct_threads_are_replies``): that transport may root
        the thread there and answer inside it, and returns that id as the
        thread's. Others ignore it. Raises ``ParallelThreadUnavailable`` with the
        sentence to answer when this chat cannot have one."""
        ...


@dataclass(frozen=True)
class ChannelBinding:
    """A live channel the runtime has started: the resource row + adapter +
    the agent defaults the channel routes to."""

    #: The channel's own row, as the gate read it at start — the row itself and
    #: not a copy of parts of it, because all three of its identifiers are
    #: wanted here: ``uid`` for the audit trail a pairing writes, ``id`` as the
    #: FK peers and threads hang off, ``name`` for the transport and the log.
    resource: Resource
    channel_type: str
    #: The agent KEY the turn platform routes by, projected from the row's
    #: ``default_agent`` uid by the gate (``wanted.Routing``).
    default_agent: str
    default_agent_config: dict[str, Any] | None
    adapter: ChannelAdapter
    # Group inbound gating (see "Configure when the bot answers in a group"), sourced
    # from the channel config.
    require_mention: bool = True
    ignore_other_mentions: bool = False
    # Quiet windows of "Take a burst of messages as one turn", from the channel config.
    wait_after_text_seconds: float = 1.5
    wait_after_forward_seconds: float = 5.0
    # "Show a turn's working state as one status line": list the step lines.
    show_steps: bool = True
    # "Ping the asker when a long turn ends": the threshold in seconds, 0 = off.
    notify_after_seconds: float = 90.0
    # "Open a new conversation after an idle period": a chat idle longer than this
    # many hours opens a new conversation on its next message; 0 never does.
    new_conversation_after_idle_hours: float = 24.0
    # The channel's framework-level ``scope`` off the row (ADR
    # per-agent-resource-scope), rewritten into agent KEYS by the gate
    # (``wanted.Routing``) — the row names agent UIDS, every reader below here
    # asks about a key. It names the agents this channel may drive; unrestricted
    # is the default and what every channel carried before scope existed. A
    # channel whose scope is empty is never bound at all: the runtime treats it
    # as dormant. So a binding that exists has already passed that gate.
    agent_scope: Scope | None = None
    # The directories `/dir` may switch into (spec channels "Choose the working
    # directory from chat"), from the channel config; empty admits none.
    directories: tuple[str, ...] = ()


class AgentCatalogPort(Protocol):
    """The slice of the agent registry the channel core needs to route by key:
    list the available agents and validate a chosen key. Satisfied structurally
    by ``AgentProviderRegistry``."""

    def agent_keys(self) -> list[str]: ...

    # ``(agent_key, display_name)`` pairs for rendering a selection card.
    def agent_choices(self) -> list[tuple[str, str]]: ...


class ModelSuggestionPort(Protocol):
    """Best-effort quick-picks for a managed agent's ``/model``
    selection card, mirroring the web picker it sits beside.

    An empty answer is ordinary: no catalogue to offer means the card falls back
    to the free-text path."""

    async def suggest(self, agent_key: str) -> list[str]: ...

    async def model_labels(self, agent_key: str) -> dict[str, str]:
        """``{id: button text}`` for the ``/model`` card, in ``suggest``'s order
        — so the card reads its choices from this one call. A card has no room
        for the web picker's name-plus-id, and a bare id can hide the one part
        that tells two choices apart (a 1M-context variant cut to
        ``claude-fable-5-…``), so the card shows a name instead."""
        ...


class ContextFetchPort(Protocol):
    """Best-effort context reader: the thread a turn lands in, and the message it
    quotes, ground the turn.

    Threads are no longer a group-@mention-only affair — SeaTalk exposes a DM
    thread endpoint too (``single_chat/get_thread_by_thread_id``, app v3.62.1+),
    so a DM thread fetches its own context exactly like a group one; ``chat_kind``
    is what picks the endpoint. Group-MAIN chatter is still never fetched
    (reading a whole group is undesirable — the group-chat-history permission is
    intentionally not granted). Platforms without a history-fetch API (Telegram's
    Bot API) satisfy this by always returning ``([], ())``."""

    async def fetch_thread(
        self, chat_id: str, thread_id: str, *, limit: int = 100, chat_kind: str = "group"
    ) -> FetchedContext:
        """Return EVERY message of the thread (all pages; ``limit`` is the page
        size) with the images/files they carry (see "Download the media a thread's
        messages carry"), so an in-thread @mention reaches the turn with the whole
        conversation and the real pictures, not dead file links. Degrades to
        ``([], ())`` on any error."""
        ...

    async def fetch_quoted(self, message_id: str) -> FetchedContext:
        """Return the one message ``message_id`` names — the message the turn
        quotes — with the images/files it carries. Degrades to ``([], ())`` on any
        error, leaving the origin block's quoted id as the only trace."""
        ...


@runtime_checkable
class EventIngestAdapter(Protocol):
    """An adapter that receives platform events pushed to it (SeaTalk, down
    the websocket connection the daemon holds) instead of polling for them."""

    async def handle_event(self, envelope: dict[str, Any]) -> None: ...
