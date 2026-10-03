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

    channel: str  # the channel resource's uid (what its adapter is named by)
    chat_id: str  # Telegram chat id / SeaTalk employee_code
    sender_display: str  # best-effort human name at the platform
    text: str
    platform_message_id: str
    timestamp: datetime
    sender_id: str = ""  # stable per-sender id for the owner gate (Telegram
    # from.id, SeaTalk employee_code); "" when the transport has none
    # The id this sender is ADDRESSED by — what an outbound @mention points at
    # ("Mention the asker in a group answer"). Deliberately NOT ``sender_id``:
    # the two are different values on SeaTalk, where the owner gate matches
    # ``employee_code`` while a mention
    # must carry ``seatalk_id``, and the docs warn that ``employee_code`` and
    # ``email`` arrive EMPTY for a sender outside the bot's organisation while
    # ``seatalk_id`` is always present. "" when the transport has no such id —
    # the reply then simply carries no mention. (Telegram's is ``from.id``; its
    # mention also carries ``sender_display`` as the link text.)
    sender_mention_id: str = ""
    # The same thing by ADDRESS, for a platform that documents a second mention
    # form (SeaTalk: ``?email=``). Only a fallback: it is precisely the field the
    # docs warn arrives empty for a sender outside the bot's organisation, so the
    # id above is what a mention is normally built from.
    sender_mention_email: str = ""
    chat_kind: str = "direct"  # "direct" | "group"
    chat_title: str = ""  # group/channel display name where the platform supplies
    # one for free (Telegram ``chat.title``); "" when it does not (SeaTalk's group
    # events carry only ``group_id``) — the origin block then names the chat by id
    # alone ("Open every turn with its message origin")
    addressed: bool = True  # DMs always; group only when @mentioned / reply-to-bot
    # group message @-mentions a non-bot user ("Configure when the bot answers
    # in a group")
    mentions_others: bool = False
    thread_id: str = ""  # non-empty when the message is inside a thread/topic
    # The message this one quotes/replies-to; "" when it quotes nothing. SeaTalk
    # delivers it on BOTH the DM (``message_from_bot_subscriber``) and the
    # group-@mention event, so it is envelope-level rather than group-only.
    # The id is scoped to the bot that received it, so the transport resolves the
    # body itself when the turn is built (spec channels "Ground a turn in the
    # message it quotes").
    quoted_message_id: str = ""
    # A forwarded chat record — rarely the whole ask, so the burst buffer waits
    # longer for the words that follow it ("Take a burst of messages as one turn").
    forwarded: bool = False
    attachments: tuple[InboundAttachment, ...] = ()  # photos/files/voice, if any
    ephemeral_id: str = ""  # set when the message itself was ephemeral (only the
    # sender and the bot can see it); it is the handle that lets the bot answer
    # privately in a group without being an administrator ("Keep non-answer
    # chatter private in a group")
    # True when a group message was sent in the group's MAIN chat on a platform
    # whose every main-chat @mention roots a fresh thread (SeaTalk): ``thread_id``
    # is then that new thread, and a command sent there configures the group's
    # defaults instead of a thread nobody will continue (spec channels "Set a
    # group's defaults from its main chat"). False everywhere else.
    group_main: bool = False


@dataclass(frozen=True)
class ReactionSet:
    """The emoji a transport marks a turn's progress with on the asker's message
    (see "Acknowledge receipt and completion by capability").

    A transport fact, not a core one: a platform may accept only a fixed list
    (Telegram's ``setMessageReaction`` does), so the adapter names emoji it knows
    will land. ``""`` skips that stage. One reaction replaces the last, so the
    message shows the turn's current state.
    """

    received: str = ""  # on receipt, before the turn starts (queued messages keep it)
    working: str = ""  # when the turn starts running
    done: str = ""  # a clean finish (a turn ending on a question for the owner too)
    failed: str = ""  # an error
    stopped: str = ""  # interrupted


@dataclass(frozen=True)
class ChannelCapabilities:
    """What a transport can do; the core picks strategies from this.

    The question the core asks about a reply surface is ``supports_live_text`` —
    *is there a surface I can keep updating while a turn runs?* ("Grow a reply in
    place on one live surface"). Telegram answers yes by editing one message;
    SeaTalk answers yes through its message **streaming** API (``init_stream`` /
    ``update_stream``). The core asks for a live-text handle (``open_live_text``)
    and never branches on which mechanism is underneath, so there is no flag for
    "can rewrite a delivered text message" — nothing would read it.
    ``supports_card_update`` is the one narrower question: can an already-delivered
    *selection card* be rewritten? Without it a card keeps offering the option the
    user already took.
    """

    supports_typing: bool  # typing indicator ack
    max_message_chars: int  # outbound chunk budget
    supports_buttons: bool = False  # interactive selection cards (ADR channel-adapter-framework)
    # An already-delivered selection card can be rewritten in place, so a card
    # stops advertising the option the user just took.
    supports_card_update: bool = False
    # An already-delivered PLAIN text message can be edited (Telegram): a short
    # system line such as "Stopping…" is then rewritten into its result rather
    # than followed by a second message.
    edits_text: bool = False
    # A surface the core can keep updating during a turn — by edit (Telegram)
    # or by streaming (SeaTalk). Drives the progress/reply strategy of "Grow a
    # reply in place on one live surface".
    supports_live_text: bool = False
    # Whether that surface BECOMES the reply, or is scaffolding thrown away at
    # the end. SeaTalk's stream persists — the message it opened is the answer,
    # grown in place — so opening it early costs nothing and is worth doing the
    # moment a turn starts, as an acknowledgement the user can see. Telegram's
    # is a status message the renderer deletes before sending the real reply, so
    # opening it early would post something only to remove it again.
    live_text_persists: bool = False
    supports_media: bool = False  # outbound file/photo upload (send_media)
    supports_history_fetch: bool = False  # can fetch recent/thread messages for context
    supports_reactions: bool = False  # emoji reaction on a message (set_reaction),
    # used for the progress marks of "Acknowledge receipt and completion by
    # capability"; transports without it fall back to the typing/working signal
    # for the same receipt cue
    reactions: ReactionSet = ReactionSet()  # which emoji, per stage
    # "Mention the asker in a group answer": how this transport spells an
    # @mention, with ``{user_id}`` standing
    # in for the id being addressed — e.g. ``"<x target=\"y?id={user_id}\"/>"``.
    # The core substitutes and prefixes; it never learns the shape. A mention
    # that also needs a display name (Telegram's inline mention is a link with
    # text) puts ``{name}`` where the name goes. A transport that cannot mention
    # declares none and its replies carry none. The
    # markup is the platform's RICH text, so every snapshot that may carry it is
    # sent as such — see ``turn_text.with_mention``.
    mention_template: str = ""
    # The same, for a transport that documents a second mention form keyed on the
    # member's EMAIL address (SeaTalk does). Used only when no id is available:
    # ``{user_id}`` stands in for the address, so one literal replace serves both.
    mention_email_template: str = ""
    # A reply-in-thread inside a direct chat is a casual reply, not a request
    # for a second conversation (SeaTalk: any message can root a thread). Such a
    # thread keys to the direct chat's own conversation unless ``/thread`` opened
    # it (see "Key conversation identity by channel, chat and thread"). False
    # where a direct-chat thread only exists because someone created it
    # (Telegram's private-chat topics), so every one is its own conversation.
    direct_threads_are_replies: bool = False
    # One or two sentences telling the agent what Markdown renders on this
    # transport (see "Tell a channel-driven agent it is on a chat channel").
    render_notes: str = ""
    # "Shape a reply for what the chat can show": whether a markdown table
    # renders (False → bullet rows + a CSV), how many lines a code block may
    # keep inline (0 = any; more → attached as a file), and whether the
    # transport collapses a ``## Details`` section itself (Telegram) — one that
    # does not may move it behind a card's button instead.
    renders_tables: bool = True
    max_inline_code_lines: int = 0
    collapses_details: bool = False


@dataclass(frozen=True)
class ChoiceButton:
    """One tappable option on an interactive selection card.

    ``value`` is the opaque callback payload echoed back when the owner taps
    (e.g. ``"agent:claude_code"`` / ``"model:claude-opus-4-8"``); it must stay
    small (Telegram caps callback_data at 64 bytes).
    """

    label: str  # human text shown on the button
    value: str  # callback payload routed back through InboundCallback.data
    # "Use the platform's button vocabulary on cards": this option is the one
    # already in effect. A transport whose
    # buttons have states shows it disabled and marked rather than re-offering
    # something tapping cannot change; one whose buttons are plain labels
    # ignores it and relies on the tick in the label instead.
    selected: bool = False
    # Shown but inactive (a page turn that runs off the end). A transport whose
    # buttons have no disabled state shows it plain; the tap changes nothing.
    disabled: bool = False


@dataclass(frozen=True)
class InboundCallback:
    """A selection-card button tap arriving from an IM chat.

    The button counterpart of ``InboundMessage``: it carries the opaque
    ``data`` (the tapped ``ChoiceButton.value``) rather than free text. The core
    owner-gates it exactly like a message before honoring the switch.
    """

    channel: str  # the channel resource's uid (what its adapter is named by)
    chat_id: str  # return address (Telegram chat id / SeaTalk group_id or employee_code)
    sender_id: str  # stable per-sender id for the owner gate ("" when none)
    data: str  # the tapped ChoiceButton.value
    callback_id: str = ""  # platform ack handle (Telegram callback_query.id); "" if none
    platform_message_id: str = ""  # the card message (for an optional in-place ack)
    chat_kind: str = "direct"  # "direct" | "group" — mirrors InboundMessage so a
    # group card tap owner-gates and replies in the group, not a DM ("Route
    # group selection-card taps back to the group")
    thread_id: str = ""  # non-empty when the card sits inside a thread/topic
    # The tapper, as a group answer to their tap must name them ("Mention the
    # asker in a group answer"): the same three values ``InboundMessage`` carries.
    sender_display: str = ""
    sender_mention_id: str = ""
    sender_mention_email: str = ""


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

    channel: str  # the channel resource's uid (what its adapter is named by)
    chat_id: str  # the group the event is about
    kind: str  # "removed_from_group" | "group_became_external"
    actor_display: str = ""  # best-effort human name of who did it (SeaTalk's
    # ``remover`` on a removal); "" when the platform says nothing about who


@dataclass(frozen=True)
class EphemeralTarget:
    """Where a group answer meant for one member is delivered.

    Spec channels "Keep non-answer chatter private in a group".

    A platform will only let an ordinary bot answer privately when it can point
    at the interaction that prompted it, and only for a short window after —
    hence the handle alongside the recipient. Exactly one handle is set.
    """

    receiver_id: str  # the member whose client shows the message
    ephemeral_message_id: str = ""  # the ephemeral message being answered
    callback_id: str = ""  # the card tap being answered


@dataclass(frozen=True)
class InboundStop:
    """The user stopped the reply from the platform's own control.

    Spec channels "Stop the turn from the platform's own stop control".

    Telegram draws a stop button on a streamed draft; pressing it reports the
    stopped draft rather than sending a message. It must reach the same
    interrupt path a typed ``/stop`` does — a stop control the user can see but
    that does not stop anything is worse than none at all.
    """

    channel: str  # the channel resource's uid (what its adapter is named by)
    chat_id: str  # the chat whose reply was stopped
    thread_id: str = ""  # the thread it was being generated in, if any
    chat_kind: str = "direct"  # "direct" | "group" — so the acknowledgement
    # routes back the way every other reply to this chat does


@dataclass(frozen=True)
class SentMessage:
    """Handle to a delivered platform message (for later edit/delete)."""

    message_id: str
