"""Live-text surfaces: one message that grows in place while a turn runs.

See "Grow a reply in place on one live surface". The core asks an adapter for a
:class:`~coffer.application.channel.ports.LiveText` handle and writes ONE code path; the mechanism
underneath differs per transport:

* Telegram edits a message it already sent (``editMessageText``).
* SeaTalk cannot edit anything, but it *can* stream: ``init_stream`` opens a
  message and each ``update_stream`` re-renders it from the FULL snapshot
  (``seatalk_live``).

The rules both transports share — one serialized writer that always sends the newest
snapshot, never more often than the buffer interval, a keep-alive only when nothing else
has written, and a dead latch on the first failure so a terminated surface is never
reused — live in :class:`LiveTextSurface` rather than being written twice.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.runtime.supervisor import spawn
from coffer.infrastructure.channel.telegram_text import clip_snapshot_utf16

_logger = logging.getLogger(__name__)

#: Transport-level buffer: never call the platform more often than this, however
#: eagerly the core offers new snapshots. This is the ONLY throttle on the path —
#: the core used to add a 1.5 s one of its own, which hid this entirely and made
#: a stream arrive a paragraph at a time.
#:
#: It is what decides how the reply READS, because the client "renders progress
#: by displaying the latest snapshot received" — it replaces the text, it does
#: not animate towards it. So the typewriter effect is made of update frequency
#: and nothing else.
#:
#: Measured against the real SDK: text deltas arrive about every 25 ms carrying
#: ~4 characters each. Buffering at SeaTalk's suggested 200 ms therefore folds
#: roughly eight of them into one visible jump of ~30 characters — a sentence at
#: a time, which is what a reader reported. Halving it halves the jump.
#:
#: 100 ms is a judgement, not a documented figure. SeaTalk publishes no rate
#: limit for ``update_stream`` at all — only the advice to buffer "approximately
#: every 200 ms" — so this trades an undocumented allowance for a visibly better
#: reply. If the platform does push back, it answers 429/code=101, the transport
#: backs off, and the refusal is logged; it cannot fail silently.
MIN_UPDATE_INTERVAL = float(os.environ.get("COFFER_SEATALK_STREAM_INTERVAL", "0.1"))

#: How often a snapshot that is NOT a pure append may be written. The client has
#: no "append": every update replaces the whole message, and a snapshot that
#: changes anything already on screen — the step lines shifting up, the clock,
#: "+N earlier" — redraws the whole bubble. A long tool run offered one of those
#: per step, so the message redrew several times a second (measured: 50 updates
#: in 12 s on a status-only stream) and visibly flickered. Text that only grows
#: at the end keeps the fast cadence above; everything else is folded into one
#: write at most this often.
REDRAW_INTERVAL = 2.0

#: Telegram edits a real message, and its flood limits (~one edit a second) are far
#: tighter than a streaming endpoint's.
TELEGRAM_UPDATE_INTERVAL = 1.5

#: One plain message's cap in UTF-16 units; the renderer clips to the far larger rich budget.
TELEGRAM_TEXT_LIMIT = 4096

#: SeaTalk terminates a stream that goes 30 s without an update, and a Telegram
#: draft is a 30-second preview: the one keep-alive cadence every live surface
#: shares. Re-send the last snapshot well inside that window so a long tool run
#: does not kill the stream (a killed stream cannot be resumed — its id is
#: rejected forever) or freeze the draft.
#:
#: 10 s, not 20. The margin matters more than it looks: the stream is now opened
#: when the TURN starts rather than when the first text arrives, so the gap the
#: keep-alive has to cover is the agent's whole thinking time, and a tick that
#: slips — a slow request, a busy loop — used to leave only 10 s of headroom
#: before the platform killed the stream. Three ticks per window instead of one
#: and a half means a single missed tick is survivable.
LIVE_KEEPALIVE_SECONDS = 10.0

#: How many keep-alive re-sends in a row — with nothing else written between
#: them — a surface may make before it gives up (10 to 15 minutes at the cadence
#: above): the bound that keeps an abandoned turn from holding a stream open
#: forever.
_KEEPALIVE_MAX_TICKS = 60


class LiveTextSurface:
    """Shared throttle + terminal-state rules for a live-updating surface.

    Subclasses implement ``_write`` (show a full snapshot) and ``_finish``
    (end the surface, returning any text the caller must still send).

    ONE writer per surface. Three callers offer snapshots — the turn's event
    loop, the renderer's status tick and this surface's own keep-alive — and
    every platform write they cause happens under one lock, carrying the NEWEST
    snapshot offered at that moment rather than the one its caller built. So a
    write can never land after a newer one, and a keep-alive can never re-send
    an older snapshot than the one already on screen. Without the lock a
    keep-alive fired while an update was in flight re-sent the previous
    snapshot under the next ``seq``, and the message jumped back to older text
    and an earlier clock before jumping forward again — the flicker a reader
    reported on SeaTalk.

    A snapshot offered inside the buffer interval is kept, not dropped: it is
    written when the interval ends, so the last words before a pause are shown
    rather than waiting for the next event. The interval depends on the
    snapshot: one that only appends to what is on screen is due after
    ``min_interval``, one that rewrites anything already shown (a redraw) after
    ``redraw_interval``.
    """

    def __init__(
        self,
        *,
        min_interval: float = MIN_UPDATE_INTERVAL,
        redraw_interval: float = REDRAW_INTERVAL,
        keepalive_seconds: float | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval = min_interval
        self._redraw_interval = max(redraw_interval, min_interval)
        self._keepalive_seconds = keepalive_seconds
        self._now = now
        self._last_write = 0.0
        #: What is on screen (the last snapshot the platform accepted) and the
        #: newest one offered — the next write always sends the latter.
        self._snapshot = ""
        self._latest = ""
        self._opened = False
        self._dead = False
        self._closing = False
        self._lock = asyncio.Lock()
        #: Diagnosis only — how many platform writes this surface has made, and
        #: when it opened. A refusal is a bare code; these say whether it came
        #: after a long silence (the platform timed the stream out) or after a
        #: burst (it is refusing the pace).
        self._writes = 0
        self._opened_at: float | None = None
        self._keepalive: asyncio.Task[None] | None = None
        self._trailing: asyncio.Task[None] | None = None

    @property
    def opened(self) -> bool:
        """Whether anything was actually delivered to the platform yet."""
        return self._opened

    async def update(self, text: str) -> None:
        text = text.strip()
        if self._dead or not text:
            return
        self._latest = text
        busy = self._lock.locked() or (self._trailing is not None and not self._trailing.done())
        if busy or (self._opened and self._now() < self._due(text)):
            # A write is in flight or the buffer is not over: the pump sends the
            # newest snapshot when it can, and this caller is not held up by it.
            self._schedule_trailing()
            return
        await self._flush()

    async def close(self, text: str) -> str:
        """Finish the surface; return what the caller must still send itself."""
        # No new interim write starts from here on, one already in flight is
        # left to land (cancelling it mid-request could not unsend it), and the
        # finishing write goes after it — so it is the last the platform sees.
        self._closing = True
        async with self._lock:
            self._stop_timers()
            if self._dead or not self._opened:
                # Never opened (or already given up): the ordinary send path owns
                # the whole reply. A dead surface is never touched again.
                self._dead = True
                return text
            self._dead = True  # terminal: this handle is spent either way
            try:
                return await self._finish(text)
            except Exception:
                return text

    # -- subclass hooks ------------------------------------------------------

    async def _write(self, text: str) -> None:
        raise NotImplementedError

    async def _finish(self, text: str) -> str:
        raise NotImplementedError

    # -- internals -----------------------------------------------------------

    async def _flush(self, *, resend: bool = False) -> bool:
        """The one write path: send the newest snapshot, under the lock.

        ``resend`` re-sends it even when it is already on screen (a keep-alive);
        otherwise an unchanged snapshot costs nothing. ``False`` when the write
        failed and the surface is now dead."""
        async with self._lock:
            text = self._latest
            if self._dead or self._closing or not text or (text == self._snapshot and not resend):
                return not self._dead
            self._last_write = self._now()
            if not await self._attempt(text):
                return False
            self._opened = True
            if self._opened_at is None:
                self._opened_at = self._last_write
            self._snapshot = text
        self._start_keepalive()
        return True

    def _due(self, text: str) -> float:
        """When ``text`` may be written: an append to what is on screen after
        the buffer interval, anything else after the redraw interval."""
        appends = text.startswith(self._snapshot)
        return self._last_write + (self._min_interval if appends else self._redraw_interval)

    def _schedule_trailing(self) -> None:
        """Start the pump unless it is already running: at most one pending
        writer per surface, and it always sends whatever is newest."""
        if self._trailing is not None and not self._trailing.done():
            return
        self._trailing = spawn(self._pump(), name="channel-live-text-flush")

    async def _pump(self) -> None:
        """Write the newest snapshot each time it falls due, until what is on
        screen is the newest one offered. The due time is re-read after every
        wait: a redraw offered while an append was waiting pushes it back."""
        try:
            while not self._dead and self._latest != self._snapshot:
                delay = self._due(self._latest) - self._now()
                if delay > 0:
                    await asyncio.sleep(delay)
                    continue
                if not await self._flush():
                    return
        finally:
            if self._trailing is asyncio.current_task():
                self._trailing = None

    async def _attempt(self, text: str) -> bool:
        """One guarded platform write: any failure latches the surface dead so a
        terminated stream / deleted message is never written to again.

        The failure is LOGGED as well as swallowed. A live surface that cannot
        open — the platform refuses the stream endpoint, the app lacks the
        scope, a rate limit — degrades to an ordinary un-streamed reply, which
        is correct behaviour but indistinguishable from "streaming was never
        attempted". Without this line the difference is invisible from the
        outside, and the only symptom is a reply that arrives all at once.

        At most one of these per surface: the ``_dead`` latch below means a
        failed surface is never written to again, so this cannot spam a turn.
        """
        self._writes += 1
        try:
            await self._write(text)
        except Exception:
            _logger.warning(
                "channel.live_text.failed",
                extra={
                    "surface": type(self).__name__,
                    "opened": self._opened,
                    # Which write, and how far into the surface's life. A refusal
                    # on the first update after a long silence means the platform
                    # timed the stream out; one after many rapid writes means it
                    # is refusing the pace. The bare error code says neither.
                    "writes": self._writes,
                    "seconds_open": (
                        None if self._opened_at is None else round(self._now() - self._opened_at, 1)
                    ),
                    "since_last_write": round(self._now() - self._last_write, 1),
                    "chars": len(text),
                },
                exc_info=True,
            )
            self._dead = True
            self._stop_timers()
            return False
        return True

    def _start_keepalive(self) -> None:
        if self._keepalive_seconds is None or self._keepalive is not None or self._dead:
            return
        self._keepalive = spawn(self._keepalive_loop(), name="channel-live-text-keepalive")

    def _stop_timers(self) -> None:
        for task in (self._keepalive, self._trailing):
            if task is not None and task is not asyncio.current_task():
                task.cancel()
        self._keepalive = None
        self._trailing = None

    async def _keepalive_loop(self) -> None:
        """Re-send the newest snapshot only when nothing else has written for a
        whole interval. A surface the renderer keeps redrawing (its status tick
        moves the clock every interval) is never re-sent at all; one left
        silent is re-sent at most 1.5 intervals after its last write.

        Bounded on purpose: a renderer whose task is cancelled mid-turn never
        closes its surface, and an unbounded loop would then re-send the same
        snapshot forever. After this many re-sends with no other write between
        them the surface gives up (the platform terminates the stream shortly
        after, as it would anyway)."""
        interval = self._keepalive_seconds or LIVE_KEEPALIVE_SECONDS
        resends = 0
        while resends < _KEEPALIVE_MAX_TICKS:
            await asyncio.sleep(interval / 2)
            if self._dead or not self._snapshot:
                return
            if self._now() - self._last_write < interval:
                resends = 0  # something else wrote: the surface is in use
                continue
            resends += 1
            if not await self._flush(resend=True):
                return
        self._dead = True


class TelegramLiveText(LiveTextSurface):
    """Telegram's live surface: send once, then edit that message in place."""

    def __init__(
        self,
        call: Callable[..., Awaitable[Any]],
        chat_id: str,
        *,
        thread_id: str = "",
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(now=now, min_interval=TELEGRAM_UPDATE_INTERVAL)
        self._call = call
        self._chat_id = chat_id
        self._thread_id = thread_id
        self._message_id = ""

    async def close(self, text: str) -> str:
        """A status message that died on a later edit is still deleted (spec channels/telegram
        "Use a deleted status message as the live scaffolding")."""
        if self._dead and self._message_id:
            return await self._finish(text)
        return await super().close(text)

    async def _write(self, text: str) -> None:
        # The cap counts UTF-16 units; the status header outlives the answer's head.
        text = clip_snapshot_utf16(text, TELEGRAM_TEXT_LIMIT)
        if not self._message_id:
            extra: dict[str, Any] = {}
            if self._thread_id:
                extra["message_thread_id"] = int(self._thread_id)
            # Interim text is PLAIN (no parse_mode): half-written markdown would
            # break Telegram's HTML parser mid-stream. Silent: it is scaffolding
            # deleted before the answer, and must not buzz a whole group.
            sent = await self._call(
                "sendMessage",
                chat_id=self._chat_id,
                text=text,
                disable_notification=True,
                **extra,
            )
            self._message_id = str(sent.get("message_id", ""))
            return
        await self._call(
            "editMessageText", chat_id=self._chat_id, message_id=self._message_id, text=text
        )

    async def _finish(self, text: str) -> str:
        # Telegram's status message is scaffolding, not the reply: delete it and
        # hand the whole text back so the caller sends it HTML-rendered and
        # paragraph-chunked (an edit cannot do either).
        with contextlib.suppress(Exception):
            await self._call("deleteMessage", chat_id=self._chat_id, message_id=self._message_id)
        self._message_id = ""  # a second close has nothing left to delete
        return text
