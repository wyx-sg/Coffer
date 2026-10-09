"""A thread read as messages: what a transport hands back when the core asks for
a thread's own messages, before anything is flattened into a turn.

The core decides which of them reach a turn (spec channels "Ground a thread
turn in a bounded slice of the thread") and which a tool call returns (spec
channels "Read a thread's earlier messages on demand"), so the transport
returns every message it could read, oldest first, with no media downloaded —
the core downloads only the media of the messages it keeps.

Pure: no platform schema. ``handle`` is the transport's own record of the
message, opaque to everything but the transport that made it, so the media of a
kept message can be downloaded later without reading the thread again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from coffer.domain.channel.rich_content import ForwardedItem

__all__ = ["ThreadMessage", "ThreadRead"]


@dataclass(frozen=True)
class ThreadMessage:
    """One message of a thread."""

    message_id: str
    sender: str
    #: When the platform says it was sent; ``None`` when it does not say.
    sent_at: datetime | None
    #: The message flattened to lines: one item, or a forwarded record's leaves.
    items: tuple[ForwardedItem, ...]
    #: The bot itself sent it.
    from_bot: bool = False
    #: It carries images or files that a media download would fetch.
    has_media: bool = False
    handle: object = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class ThreadRead:
    """A thread's messages, oldest first."""

    messages: tuple[ThreadMessage, ...] = ()
    #: A sentence on what the platform's thread read cannot return for this
    #: thread (spec channels "Say what a thread read cannot show"); "" when
    #: nothing is missing.
    window_note: str = ""
    #: The read failed outright. A failure is not an empty thread: a turn still
    #: runs without context, but a tool call says the read failed.
    failed: bool = False
