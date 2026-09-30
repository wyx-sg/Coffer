"""What a reply typed on the web knows about the channel it may also reach
(spec chat "Mirror a web reply into the channel it came from").

Shared by both kinds: the chat kind reads these through its ``ChannelMirrorPort``
and the channel kind builds them — chat never imports channel code, so the
values that cross the seam live here, in the domain both may import.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

__all__ = [
    "ChannelPlaceView",
    "MirrorResult",
    "MirrorState",
    "MirrorView",
    "UndeliveredReply",
]

#: What became of a mirrored reply: ``sent`` to the chat now, ``pending`` in the
#: channel's outbox until it can send, or ``kept`` in Coffer only (a group's
#: main chat, or a conversation no chat can be found for).
MirrorState = Literal["sent", "pending", "kept"]


@dataclass(frozen=True)
class UndeliveredReply:
    """One message Coffer still owes the chat: a web ``reply`` or the agent's
    ``answer`` to it."""

    kind: str
    text: str
    created_at: datetime


@dataclass(frozen=True)
class MirrorView:
    """Where a reply on this conversation will also go, before it is sent.

    ``target`` is the label the page shows ("SeaTalk · 🧵#1 deploy check");
    ``reason`` says why a reply is not deliverable (``group_main``,
    ``not_located``, ``chat_kind_unknown``, ``channel_deleted``) and is ``None``
    when it is."""

    deliverable: bool
    platform: str
    channel: str | None
    target: str
    reason: str | None
    undelivered: tuple[UndeliveredReply, ...] = ()


@dataclass(frozen=True)
class MirrorResult:
    """The outcome of mirroring one reply, and the ``on_start`` sink its turn is
    queued with: rendering the answer into the chat (``sent``), collecting it
    for later delivery (``pending``), or nothing (``kept``)."""

    state: MirrorState
    on_start: Callable[[asyncio.Queue[Any]], None] | None = None


@dataclass(frozen=True)
class ChannelPlaceView:
    """Where in its channel a conversation lives, for the Conversations list's
    source badge (spec chat "Show every conversation on the Conversations page").

    ``chat_kind`` is ``direct`` / ``group`` (``None`` when never learnt);
    ``thread`` says the conversation lives in a thread or topic rather than the
    chat's main timeline; ``parallel_mark`` is the ``🧵#N title`` of a
    ``/thread`` parallel conversation; ``chat_name`` is the group's display name
    when Coffer knows one."""

    chat_kind: str | None
    thread: bool
    parallel_mark: str | None = None
    chat_name: str | None = None
