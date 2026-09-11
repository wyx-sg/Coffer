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
import time
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.render import chunk_text, markdown_to_seatalk
from coffer.infrastructure.channel.seatalk_parse import split_to_byte_limit

_logger = logging.getLogger(__name__)

#: Transport-level buffer: never call the platform more often than this, however
#: eagerly the core offers new snapshots (the core has its own, coarser cadence).
#: SeaTalk's guidance is ~200 ms — do not update per token.
MIN_UPDATE_INTERVAL = 0.2

#: SeaTalk terminates a stream that goes 30 s without an update. Re-send the
#: last snapshot well inside that window so a long tool run does not kill the
#: stream (a killed stream cannot be resumed — its id is rejected forever).
_STREAM_KEEPALIVE_SECONDS = 20.0

#: How many keep-alive ticks a surface may spend with no new content before it
#: gives up (~10 minutes) — the bound that keeps an abandoned turn from holding
#: a stream open forever.
_KEEPALIVE_MAX_TICKS = 30

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
        try:
            await self._write(text)
        except Exception:
            _logger.warning(
                "channel.live_text.failed",
                extra={"surface": type(self).__name__, "opened": self._opened},
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
        super().__init__(now=now)
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

    Platform contract (published docs, 2026-09-09): every update carries the
    whole accumulated text (never a delta), updates must not be more than 30 s
    apart, a stream carries at most 4096 characters, and once a stream ends
    (finished, timed out, or errored) any request naming its id is rejected.
    Older clients (< 3.67) simply see the finished message when it closes.
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

    def _message(self, text: str) -> dict[str, Any]:
        message: dict[str, Any] = {"tag": "text", "text": {"format": 1, "content": text}}
        if self._thread_id:
            # Same verified placement as an ordinary send: thread_id goes INSIDE
            # the message body (a top-level one is ignored).
            message["thread_id"] = self._thread_id
        return message

    async def _write(self, text: str) -> None:
        if not self._stream_id:
            payload = {**self._target()}
            if self._thread_id:
                payload["thread_id"] = self._thread_id
            result = await self._post(f"/messaging/v2/{self._surface}/init_stream", payload)
            stream_id = str((result or {}).get("stream_id", "")) if isinstance(result, dict) else ""
            if not stream_id:
                raise ChannelSendFailed(self._name, "init_stream returned no stream_id")
            self._stream_id = stream_id
        # Interim snapshots go out as plain text clipped to the stream budget —
        # partial markdown mid-stream would render as noise.
        await self._update(_clip_tail_bytes(text, _STREAM_BYTE_BUDGET), finish=False)

    async def _finish(self, text: str) -> str:
        head, remainder = _split_for_stream(text or self._snapshot)
        # The streamed message IS the SeaTalk reply (nothing can delete it), so
        # the final snapshot is markdown-rendered like any other SeaTalk send.
        await self._update(markdown_to_seatalk(head), finish=True)
        return remainder

    async def _update(self, text: str, *, finish: bool) -> None:
        self._seq += 1  # the platform requires a monotonic seq, starting at 1
        await self._post(
            f"/messaging/v2/{self._surface}/update_stream",
            {
                "stream_id": self._stream_id,
                "seq": self._seq,
                "message": self._message(text),
                "finish": finish,
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
