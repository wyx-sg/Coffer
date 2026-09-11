"""Normalized message envelopes — the only shapes the channel core sees.

Adapters translate platform payloads (Telegram updates, SeaTalk events) to
and from these; nothing above the adapter layer knows a platform schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InboundAttachment:
    """A file (photo/document/voice) the transport downloaded for an inbound message.

    The bytes are already saved to a local path; the core converts this to a
    chat-domain ``Attachment`` when driving the turn. Modality-neutral so a new
    media type is a new ``mime``, not a new envelope.
    """

    path: str  # absolute local path the transport downloaded the bytes to
    mime: str  # e.g. "image/jpeg", "application/pdf", "audio/ogg"
    filename: str  # best-effort original / synthesized name


@dataclass(frozen=True)
class InboundMessage:
    """A message arriving from an IM chat — text and/or downloaded attachments."""

    channel: str  # channel resource name
    chat_id: str  # Telegram chat id / SeaTalk employee_code
    sender_display: str  # best-effort human name at the platform
    text: str
    platform_message_id: str
    timestamp: datetime
    sender_id: str = ""  # stable per-sender id for the owner gate (Telegram
    # from.id, SeaTalk employee_code); "" when the transport has none
    chat_kind: str = "direct"  # "direct" | "group"
    chat_title: str = ""  # group/channel display name where the platform supplies
    # one for free (Telegram ``chat.title``); "" when it does not (SeaTalk's group
    # events carry only ``group_id``) — the origin block then names the chat by id
    # alone (FR-042)
    addressed: bool = True  # DMs always; group only when @mentioned / reply-to-bot
    mentions_others: bool = False  # group message @-mentions a non-bot user (FR-035)
    thread_id: str = ""  # non-empty when the message is inside a thread/topic
    # The message this one quotes/replies-to; "" when it quotes nothing. SeaTalk
    # delivers it on BOTH the DM (``message_from_bot_subscriber``) and the
    # group-@mention event, so it is envelope-level rather than group-only.
    # Coffer surfaces the id and deliberately does NOT resolve the quoted body
    # itself: that lookup (``get_message_by_message_id``) is an agent-invoked MCP
    # tool, so the transport's job ends at telling the agent that a quote exists
    # and what its id is — the agent fetches the body only when it needs it.
    quoted_message_id: str = ""
    attachments: tuple[InboundAttachment, ...] = ()  # photos/files/voice, if any


@dataclass(frozen=True)
class ChannelCapabilities:
    """What a transport can do; the core picks strategies from this.

    ``supports_edit`` and ``supports_live_text`` are easy to confuse, so keep
    the distinction sharp (FR-037):

    * ``supports_edit`` is literal — the transport can rewrite a message it
      already delivered (Telegram ``editMessageText``). ``edit_text`` raises
      on a transport without it.
    * ``supports_live_text`` is the question the core actually asks — *is
      there a surface I can keep updating while a turn runs?* Telegram
      answers yes by editing; SeaTalk answers yes through its message
      **streaming** API (``init_stream`` / ``update_stream``), which grows one
      message in place while being unable to edit anything. The core asks for
      a live-text handle (``open_live_text``) and never branches on which
      mechanism is underneath.
    * ``supports_card_update`` is narrower than either: can an already-delivered
      *selection card* be rewritten? SeaTalk answers yes here while answering no
      to ``supports_edit`` — its update API applies to interactive cards only,
      never to a text message. Without it a card keeps offering the option the
      user already took.
    """

    supports_edit: bool  # can rewrite an already-delivered message (edit_text)
    supports_typing: bool  # typing indicator ack
    max_message_chars: int  # outbound chunk budget
    supports_buttons: bool = False  # interactive selection cards (ADR channel-adapter-framework)
    # An already-delivered selection card can be rewritten in place, so a card
    # stops advertising the option the user just took. Narrower than
    # supports_edit: SeaTalk can update a card but not a text message.
    supports_card_update: bool = False
    # A surface the core can keep updating during a turn — by edit (Telegram)
    # or by streaming (SeaTalk). Drives the FR-037 progress/reply strategy.
    supports_live_text: bool = False
    supports_media: bool = False  # outbound file/photo upload (send_media)
    supports_groups: bool = False  # group-chat send path exists
    supports_history_fetch: bool = False  # can fetch recent/thread messages for context
    supports_reactions: bool = False  # emoji reaction on a message (set_reaction),
    # used for the FR-036 receipt (👀) + completion (✅) ack; transports without
    # it fall back to the typing/working signal for the same receipt cue


@dataclass(frozen=True)
class ChoiceButton:
    """One tappable option on an interactive selection card.

    ``value`` is the opaque callback payload echoed back when the owner taps
    (e.g. ``"agent:claude_code"`` / ``"model:claude-opus-4-8"``); it must stay
    small (Telegram caps callback_data at 64 bytes).
    """

    label: str  # human text shown on the button
    value: str  # callback payload routed back through InboundCallback.data


@dataclass(frozen=True)
class InboundCallback:
    """A selection-card button tap arriving from an IM chat.

    The button counterpart of ``InboundMessage``: it carries the opaque
    ``data`` (the tapped ``ChoiceButton.value``) rather than free text. The core
    owner-gates it exactly like a message before honoring the switch.
    """

    channel: str  # channel resource name
    chat_id: str  # return address (Telegram chat id / SeaTalk group_id or employee_code)
    sender_id: str  # stable per-sender id for the owner gate ("" when none)
    data: str  # the tapped ChoiceButton.value
    callback_id: str = ""  # platform ack handle (Telegram callback_query.id); "" if none
    platform_message_id: str = ""  # the card message (for an optional in-place ack)
    chat_kind: str = "direct"  # "direct" | "group" — mirrors InboundMessage so a
    # group card tap owner-gates and replies in the group, not a DM (FR-034)
    thread_id: str = ""  # non-empty when the card sits inside a thread/topic


@dataclass(frozen=True)
class InboundLifecycle:
    """A non-message platform event about the bot's own standing in a chat.

    Deliberately NOT an ``InboundMessage``/``InboundCallback``: those two both
    start or steer a turn, while these never do — they change what the binding
    IS (the bot was removed from the group; the group became external, so people
    from other organisations can now read what lands there). Routing them
    through the message path would force every consumer above the adapter to
    filter them back out before doing anything.

    ``kind`` is a closed string set rather than an enum, matching how
    ``chat_kind`` is already modelled in this module.
    """

    channel: str  # channel resource name
    chat_id: str  # the group the event is about
    kind: str  # "removed_from_group" | "group_became_external"
    actor_display: str = ""  # best-effort human name of who did it (SeaTalk's
    # ``remover`` on a removal); "" when the platform says nothing about who


@dataclass(frozen=True)
class SentMessage:
    """Handle to a delivered platform message (for later edit/delete)."""

    message_id: str
