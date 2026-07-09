"""Telegram album debounce (FR-038): buffer messages sharing a ``media_group_id``
and flush them as ONE inbound turn.

Split out of ``telegram.py`` to keep that module under the file-size limit. The
Bot API delivers a multi-photo album as SEPARATE update messages that share a
``media_group_id`` (the caption rides the first item only). Each item's
attachments are appended to a per-group buffer and a short debounce timer is
(re)armed; when no new item arrives within the window the buffer flushes the
group as a single turn carrying every attachment and the album's caption. A lone
item that never gets siblings still flushes after the window as a normal
single-attachment turn.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from coffer.domain.channel.envelopes import InboundAttachment

__all__ = ["AlbumBuffer", "FlushCallback"]

# ``(representative_message, all_attachments) -> awaitable`` — emits the turn.
FlushCallback = Callable[[dict[str, Any], tuple[InboundAttachment, ...]], Awaitable[None]]


@dataclass
class _Album:
    """One in-flight album: its representative message (the caption source) and
    the attachments accumulated across items, in arrival order."""

    message: dict[str, Any]
    attachments: list[InboundAttachment] = field(default_factory=list)


class AlbumBuffer:
    """Debounce album items into one flush per ``media_group_id``.

    ``add`` is called from the poll loop for each item carrying a
    ``media_group_id``; ``cancel_all`` (on adapter stop) drops pending timers and
    any in-flight flush tasks so nothing leaks past the transport's lifetime.
    """

    def __init__(self, debounce_seconds: float, on_flush: FlushCallback) -> None:
        self._debounce = debounce_seconds
        self._on_flush = on_flush
        self._albums: dict[str, _Album] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def add(
        self,
        group_id: str,
        message: dict[str, Any],
        attachments: tuple[InboundAttachment, ...],
    ) -> None:
        """Append one album item's attachments and (re)arm its debounce timer."""
        album = self._albums.get(group_id)
        if album is None:
            album = _Album(message=message)
            self._albums[group_id] = album
        elif message.get("caption") and not album.message.get("caption"):
            # Telegram puts the caption on the first item; prefer whichever item
            # actually carries it as the text source for the flushed turn.
            album.message = message
        album.attachments.extend(attachments)
        self._rearm(group_id)

    def _rearm(self, group_id: str) -> None:
        loop = asyncio.get_running_loop()
        existing = self._timers.pop(group_id, None)
        if existing is not None:
            existing.cancel()
        self._timers[group_id] = loop.call_later(self._debounce, self._fire, group_id)

    def _fire(self, group_id: str) -> None:
        self._timers.pop(group_id, None)
        album = self._albums.pop(group_id, None)
        if album is None:
            return
        task = asyncio.ensure_future(self._on_flush(album.message, tuple(album.attachments)))
        self._tasks.add(task)
        task.add_done_callback(lambda _t: self._tasks.discard(task))

    def cancel_all(self) -> None:
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        self._albums.clear()
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
