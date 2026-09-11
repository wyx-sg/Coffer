"""Live-text surfaces: one message that grows in place while a turn runs.

FR-037. The core asks an adapter for a :class:`~coffer.application.channel.ports.LiveText`
handle and writes ONE code path; the mechanism underneath differs per transport:

* Telegram edits a message it already sent (``editMessageText``).
* SeaTalk cannot edit anything, but it *can* stream: ``init_stream`` opens a
  message and each ``update_stream`` re-renders it from the FULL snapshot.

The rules both transports share — never call the platform more often than the
buffer interval, remember the last snapshot, and latch dead on the first
failure so a terminated surface is never reused — live in
:class:`LiveTextSurface` here rather than being written twice.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.render import chunk_text, markdown_to_seatalk
from coffer.infrastructure.channel.seatalk_parse import split_to_byte_limit

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

#: Telegram edits a real message to show progress, and its flood limits are far
#: tighter than a streaming endpoint's — roughly one edit a second before it
#: starts refusing them. It keeps the cadence the core used to impose on
#: everyone.
TELEGRAM_UPDATE_INTERVAL = 1.5

#: SeaTalk terminates a stream that goes 30 s without an update. Re-send the
#: last snapshot well inside that window so a long tool run does not kill the
#: stream (a killed stream cannot be resumed — its id is rejected forever).
#:
#: 10 s, not 20. The margin matters more than it looks: the stream is now opened
#: when the TURN starts rather than when the first text arrives, so the gap the
#: keep-alive has to cover is the agent's whole thinking time, and a tick that
#: slips — a slow request, a busy loop — used to leave only 10 s of headroom
#: before the platform killed the stream. Three ticks per window instead of one
#: and a half means a single missed tick is survivable.
_STREAM_KEEPALIVE_SECONDS = 10.0

#: How many keep-alive ticks a surface may spend with no new content before it
#: gives up (~10 minutes at the tick above) — the bound that keeps an abandoned
#: turn from holding a stream open forever.
_KEEPALIVE_MAX_TICKS = 60

#: How much of a reply one SeaTalk stream may carry. The platform caps a stream
#: at 4096 characters; this budget is in UTF-8 BYTES (CJK is 3 bytes/char) and
#: leaves headroom for the markdown escaping the final snapshot adds. Anything
#: past it is handed back to the caller and sent as ordinary chunked messages.
_STREAM_BYTE_BUDGET = 3600


class LiveTextSurface:
    """Shared throttle + terminal-state rules for a live-updating surface.

    Subclasses implement ``_write`` (show a full snapshot) and ``_finish``
    (end the surface, returning any text the caller must still send).
    """

    def __init__(
        self,
        *,
        min_interval: float = MIN_UPDATE_INTERVAL,
        keepalive_seconds: float | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval = min_interval
        self._keepalive_seconds = keepalive_seconds
        self._now = now
        self._last_write = 0.0
        self._snapshot = ""
        self._opened = False
        self._dead = False
        #: Diagnosis only — how many platform writes this surface has made, and
        #: when it opened. A refusal is a bare code; these say whether it came
        #: after a long silence (the platform timed the stream out) or after a
        #: burst (it is refusing the pace).
        self._writes = 0
        self._opened_at: float | None = None
        self._keepalive: asyncio.Task[None] | None = None

    @property
    def opened(self) -> bool:
        """Whether anything was actually delivered to the platform yet."""
        return self._opened

    async def update(self, text: str) -> None:
        text = text.strip()
        if self._dead or not text or text == self._snapshot:
            return
        now = self._now()
        if self._opened and now - self._last_write < self._min_interval:
            return
        self._last_write = now
        if not await self._attempt(text):
            return
        self._opened = True
        if self._opened_at is None:
            self._opened_at = now
        self._snapshot = text
        self._start_keepalive()

    async def close(self, text: str) -> str:
        """Finish the surface; return what the caller must still send itself."""
        self._stop_keepalive()
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
            self._stop_keepalive()
            return False
        return True

    def _start_keepalive(self) -> None:
        if self._keepalive_seconds is None or self._keepalive is not None:
            return
        self._keepalive = asyncio.create_task(self._keepalive_loop())

    def _stop_keepalive(self) -> None:
        if self._keepalive is not None:
            self._keepalive.cancel()
            self._keepalive = None

    async def _keepalive_loop(self) -> None:
        # Bounded on purpose: a renderer whose task is cancelled mid-turn never
        # closes its surface, and an unbounded loop would then re-send the same
        # snapshot forever. After this many silent ticks the surface gives up
        # (the platform terminates the stream shortly after, as it would anyway).
        for _ in range(_KEEPALIVE_MAX_TICKS):
            await asyncio.sleep(self._keepalive_seconds or _STREAM_KEEPALIVE_SECONDS)
            if self._dead or not self._snapshot:
                return
            self._last_write = self._now()
            if not await self._attempt(self._snapshot):
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

    async def _write(self, text: str) -> None:
        if not self._message_id:
            extra: dict[str, Any] = {}
            if self._thread_id:
                extra["message_thread_id"] = int(self._thread_id)
            # Interim text is PLAIN (no parse_mode): half-written markdown would
            # break Telegram's HTML parser mid-stream.
            sent = await self._call("sendMessage", chat_id=self._chat_id, text=text, **extra)
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
        return text


class SeaTalkLiveText(LiveTextSurface):
    """SeaTalk's live surface: ``init_stream`` once, then ``update_stream`` with
    the full snapshot each time, finishing with ``finish: true``.

    Platform contract, re-read from the published docs on 2026-09-11 after the
    first implementation was refused live with ``code=102``:

    * ``init_stream`` takes the target AND a mandatory ``message`` — it posts a
      real placeholder message to the chat and returns the ``stream_id``. A body
      carrying only the target is rejected, which is what happened.
    * ``update_stream`` ALSO takes the target. ``stream_id`` alone does not
      identify the destination, and omitting it is refused the same way.
    * ``message`` is shaped differently either side: ``init`` names the kind
      (``tag``), every ``update`` carries only the content object, because the
      kind was fixed when the stream opened.
    * Every update carries the whole accumulated text, never a delta — the
      client renders the latest snapshot it has.
    * ``seq`` starts at 1 on the first ``update_stream`` and increments by one;
      ``init_stream`` consumes none.
    * Updates must be less than 30 s apart, total content is capped at 4096
      characters, and once a stream ends (finished, timed out, errored) any
      request naming its id is rejected.
    * ``format`` is 1 for Markdown and 2 for plain text. Interim snapshots go
      out as 2: a reply cut mid-word can end inside an unclosed ``*`` or ``_``,
      and asking the client to parse that renders noise.
    * Streaming needs no permission of its own — it rides the same Send Message
      grant as an ordinary reply. Older clients (< 3.67) simply see the finished
      message when the stream closes.
    """

    def __init__(
        self,
        post: Callable[[str, dict[str, Any]], Awaitable[Any]],
        chat_id: str,
        *,
        name: str = "seatalk",
        thread_id: str = "",
        chat_kind: str = "direct",
        now: Callable[[], float] = time.monotonic,
        keepalive_seconds: float = _STREAM_KEEPALIVE_SECONDS,
    ) -> None:
        super().__init__(keepalive_seconds=keepalive_seconds, now=now)
        self._post = post
        self._name = name
        self._chat_id = chat_id
        self._thread_id = thread_id
        self._surface = "group_chat" if chat_kind == "group" else "single_chat"
        self._stream_id = ""
        self._seq = 0

    def _target(self) -> dict[str, Any]:
        key = "group_id" if self._surface == "group_chat" else "employee_code"
        return {key: self._chat_id}

    def _content(self, text: str, *, markdown: bool) -> dict[str, Any]:
        """The ``text`` object both endpoints carry. ``format`` 2 is plain."""
        return {"format": 1 if markdown else 2, "content": text}

    async def _open(self, text: str) -> None:
        """``init_stream``: post the opening message and keep its stream id.

        The opening message is the first snapshot rather than a "Thinking…"
        placeholder — it is a real message either way, so it may as well carry
        what we already have. It consumes no ``seq``.
        """
        message: dict[str, Any] = {
            "tag": "text",
            "text": self._content(text, markdown=False),
        }
        if self._thread_id:
            # Same verified placement as an ordinary send, and as the docs'
            # own sample: thread_id goes INSIDE the message body.
            message["thread_id"] = self._thread_id
        result = await self._post(
            f"/messaging/v2/{self._surface}/init_stream",
            {**self._target(), "message": message},
        )
        stream_id = str((result or {}).get("stream_id", "")) if isinstance(result, dict) else ""
        if not stream_id:
            raise ChannelSendFailed(self._name, "init_stream returned no stream_id")
        self._stream_id = stream_id

    async def _write(self, text: str) -> None:
        # Interim snapshots are clipped to the stream budget and sent as plain
        # text; the caller's markdown is rendered once, in the final snapshot.
        clipped = _clip_tail_bytes(text, _STREAM_BYTE_BUDGET)
        if not self._stream_id:
            await self._open(clipped)
            return
        await self._update(clipped, finish=False, markdown=False)

    async def _finish(self, text: str) -> str:
        head, remainder = _split_for_stream(text or self._snapshot)
        # The streamed message IS the SeaTalk reply (nothing can delete it), so
        # the final snapshot is markdown-rendered like any other SeaTalk send.
        await self._update(markdown_to_seatalk(head), finish=True, markdown=True)
        return remainder

    async def _update(self, text: str, *, finish: bool, markdown: bool) -> None:
        self._seq += 1  # the platform requires a monotonic seq, starting at 1
        await self._post(
            f"/messaging/v2/{self._surface}/update_stream",
            {
                # The target is mandatory here too: a stream_id alone does not
                # tell the platform which chat to update.
                **self._target(),
                "stream_id": self._stream_id,
                "seq": self._seq,
                "finish": finish,
                # No `tag` on an update — the kind was fixed by init_stream.
                "message": {"text": self._content(text, markdown=markdown)},
            },
        )


def _clip_tail_bytes(text: str, budget: int) -> str:
    """Keep the TAIL of ``text`` within ``budget`` UTF-8 bytes, behind a leading
    ellipsis — an interim snapshot shows the newest words, not the oldest."""
    if len(text.encode("utf-8")) <= budget:
        return text
    return "…" + split_to_byte_limit(text, budget)[-1]


def _split_for_stream(text: str) -> tuple[str, str]:
    """``(head, remainder)``: the most a stream may carry, and the rest.

    A reply's length is unknown until it ends, so a stream that overruns the
    platform's per-stream cap finishes at the limit and the remainder is handed
    back to be sent as ordinary chunked messages — the alternative (refusing to
    stream anything that *might* grow too long) would withhold the live reply
    from every turn to serve the rare one.
    """
    if len(text.encode("utf-8")) <= _STREAM_BYTE_BUDGET:
        return text, ""
    chunks = chunk_text(text, _STREAM_BYTE_BUDGET)  # paragraph-aware first
    pieces = split_to_byte_limit(chunks[0], _STREAM_BYTE_BUDGET)  # then byte-safe
    rest = [part for part in ["".join(pieces[1:]), *chunks[1:]] if part]
    return pieces[0], "\n\n".join(rest)
