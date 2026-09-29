"""SeaTalk's live surface: one streamed message that grows into the reply.

Split out of ``live_text`` (at its size budget); the shared throttle, keep-alive
and dead-latch rules stay there in :class:`LiveTextSurface`.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.live_text import LIVE_KEEPALIVE_SECONDS, LiveTextSurface
from coffer.infrastructure.channel.render import markdown_to_seatalk
from coffer.infrastructure.channel.seatalk_stream_text import (
    _split_for_stream,
    interim_snapshot,
)

__all__ = ["SeaTalkLiveText"]


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
    * ``format`` is 1 for Markdown and 2 for plain text. EVERY snapshot here is
      1, including the opening one — an @mention is markup, and the platform
      decides @ notifications when a message is created, so the mention has to
      be in what ``init_stream`` posts ("Mention the asker in a group answer"). Interim snapshots
      used to go out as 2 to keep a reply cut mid-word from being parsed as half a markdown run;
      that protection now comes from ESCAPING the partial text (``interim_snapshot``) instead of
      from asking for plain text.
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
        keepalive_seconds: float = LIVE_KEEPALIVE_SECONDS,
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

    def _content(self, text: str) -> dict[str, Any]:
        """The ``text`` object both endpoints carry. ``format: 1`` is SeaTalk
        markdown, and every snapshot uses it — the message must be able to carry
        an @mention from the moment it is created, and a tag in a
        ``format: 2`` message would reach the reader as its own literal source.
        Partial text is kept literal by escaping it, not by dropping to plain."""
        return {"format": 1, "content": text}

    async def _open(self, text: str) -> None:
        """``init_stream``: post the opening message and keep its stream id.

        The opening message is the first snapshot rather than a "Thinking…"
        placeholder — it is a real message either way, so it may as well carry
        what we already have. It consumes no ``seq``.

        It is also where an @mention has to land: the platform decides @
        notifications when the message is CREATED, never on a later update, so a
        mention added only to the finished snapshot renders as a name and
        notifies nobody. That cost a live debugging round.
        """
        message: dict[str, Any] = {
            "tag": "text",
            "text": self._content(text),
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
        # An in-flight snapshot is clipped to the stream budget and escaped (its
        # @mention kept whole at the head); the caller's markdown is RENDERED
        # once, in the final snapshot.
        snapshot = interim_snapshot(text)
        if not self._stream_id:
            await self._open(snapshot)
            return
        await self._update(snapshot, finish=False)

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
                # The target is mandatory here too: a stream_id alone does not
                # tell the platform which chat to update.
                **self._target(),
                "stream_id": self._stream_id,
                "seq": self._seq,
                "finish": finish,
                # No `tag` on an update — the kind was fixed by init_stream.
                "message": {"text": self._content(text)},
            },
        )
