"""Where in its channel a conversation lives (spec chat "Show every conversation
on the Conversations page").

Shared by both kinds: the chat kind reads it through its ``ChannelPlacesPort``
and the channel kind builds it — chat never imports channel code, so the value
that crosses the seam lives here, in the domain both may import.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ChannelPlaceView"]


@dataclass(frozen=True)
class ChannelPlaceView:
    """Where in its channel a conversation lives, for the Conversations list's
    source badge.

    ``chat_kind`` is ``direct`` / ``group`` (``None`` when never learnt);
    ``thread`` says the conversation lives in a thread or topic rather than the
    chat's main timeline; ``parallel_mark`` is the ``🧵#N title`` of a
    ``/thread`` parallel conversation; ``chat_name`` is the group's display name
    when Coffer knows one."""

    chat_kind: str | None
    thread: bool
    parallel_mark: str | None = None
    chat_name: str | None = None
