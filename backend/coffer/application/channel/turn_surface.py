"""The one live surface a turn owns, and the typing heartbeat beside it.

Split out of ``turn_render`` (at its size budget). ``TurnSurface`` is the only
code that talks to a ``LiveText`` handle: it opens one lazily (asking the
transport once per turn, whatever the answer), hands it every snapshot — the
@mention applied in exactly one place — and closes it with the final body. A
transport with no surface, or one that refuses to open it, gets no interim
traffic at all; its final reply is the whole signal.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from coffer.application.channel.ports import ChannelAdapter, LiveText

__all__ = ["TurnSurface", "typing_heartbeat"]

_logger = logging.getLogger(__name__)


@dataclass
class TurnSurface:
    """One turn's live surface (see "Grow a reply in place on one live surface")."""

    adapter: ChannelAdapter
    chat_id: str
    thread_id: str
    chat_kind: str
    #: Opens a snapshot with the asker's @mention where that is right. Applied to
    #: every snapshot of a surface that PERSISTS as the reply, because a platform
    #: decides @ notifications when a message is created (see
    #: ``turn_text.with_mention``); a scaffolding surface is deleted, so it carries
    #: none and its snapshots stay plain.
    mention: Callable[[str], str]
    live: LiveText | None = None
    tried: bool = False
    #: Whether a surface that persists as the reply was actually opened — the
    #: reply then lives in a message created when the turn began.
    persisted: bool = False

    @property
    def is_open(self) -> bool:
        return self.live is not None

    def _snapshot(self, text: str) -> str:
        return self.mention(text) if self.adapter.capabilities.live_text_persists else text

    async def show(self, text: str) -> None:
        """Offer one snapshot, opening the surface on the first. No throttle:
        ``update`` is a no-op inside the surface's own interval and when the
        snapshot has not changed, so the transport renders at the cadence it
        can sustain."""
        if self.live is None:
            await self.open(text)
            return
        with contextlib.suppress(Exception):
            await self.live.update(self._snapshot(text))

    @property
    def available(self) -> bool:
        """Whether this turn may have a live surface at all: the transport has one,
        and — in a group — it may stream there. SeaTalk's stream cannot be rewritten
        afterwards, so a group reply there is a card the owner can withdraw instead
        (spec channels/seatalk "Send group replies as withdrawable cards")."""
        caps = self.adapter.capabilities
        if not caps.supports_live_text:
            return False
        return not (self.chat_kind == "group" and not caps.streams_in_groups)

    async def open(self, text: str) -> None:
        if self.tried or not self.available:
            return
        self.tried = True  # ask once per turn, whatever the answer
        try:
            self.live = await self.adapter.open_live_text(
                self.chat_id, thread_id=self.thread_id, chat_kind=self.chat_kind
            )
        except Exception:
            # Swallowed so a transport that cannot stream still answers, but
            # logged: the degraded result — a reply delivered in one piece —
            # looks exactly like a turn that never tried to stream.
            _logger.warning("channel.live_text.open_failed", exc_info=True)
            return
        if self.live is None:
            return
        self.persisted = self.adapter.capabilities.live_text_persists
        with contextlib.suppress(Exception):
            await self.live.update(self._snapshot(text))

    async def close(self, body: str) -> str:
        """Finish the surface with ``body``; return what must still be sent."""
        live, self.live = self.live, None
        if live is None:
            return body
        try:
            return await live.close(body)
        except Exception:
            # A surface that failed to close is spent, never retried — the
            # ordinary send path still owes the user the reply.
            return body


async def typing_heartbeat(
    adapter: ChannelAdapter, chat_id: str, thread_id: str, chat_kind: str, seconds: float
) -> None:
    """Re-send the typing indicator every ``seconds`` until cancelled.

    Best-effort: a failed heartbeat never breaks the turn."""
    while True:
        await asyncio.sleep(seconds)
        with contextlib.suppress(Exception):
            await adapter.send_typing(chat_id, thread_id=thread_id, chat_kind=chat_kind)
