"""Telegram's own streaming surface: a message draft (see "Stream through
the platform's own surface where the chat has one").

Before Bot API 10.1 the only way to show a reply growing was to send a message
and keep rewriting it — which meant a status message to delete afterwards, an
edit-rate ceiling on how often progress could show, and a rewrite of something
already delivered to the chat.

``sendMessageDraft`` is the purpose-built alternative: a partial message streamed
to the user as a temporary preview while it is being generated, never persisted,
and replaced by the real ``sendMessage`` once the text is final. It also carries
``can_stop``, which makes the platform draw the stop control that is routed
back into Coffer's interrupt path.

The handle here is therefore *simpler* than the edit-based one it replaces: it
has nothing to clean up, because a draft expires on its own.

**Private chats only.** ``sendMessageDraft`` takes "the target private chat" —
there is no group form of it. A group turn keeps the edit-based surface, which
is why the adapter chooses between them rather than always preferring this one.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.channel.turn_status import split_snapshot
from coffer.infrastructure.channel.live_text import LIVE_KEEPALIVE_SECONDS, LiveTextSurface
from coffer.infrastructure.channel.telegram_features import Feature, is_unsupported
from coffer.infrastructure.channel.telegram_rich import normalize_rich_markdown
from coffer.infrastructure.channel.telegram_text import clip_snapshot_utf16

__all__ = ["TelegramDraftLiveText", "draft_markdown", "new_draft_id"]

Call = Callable[..., Awaitable[Any]]

#: A draft is a 30-second preview, so it is refreshed on the one keep-alive
#: cadence every live surface shares
#: (``live_text.LIVE_KEEPALIVE_SECONDS``), well inside it, or the user watches
#: a frozen half-reply through a long tool run.

#: What one draft may carry: "0-4096 characters after entities parsing". A
#: snapshot past it is refused, which would kill the surface mid-reply — so the
#: TAIL is kept behind an ellipsis instead — the newest words being the ones worth watching.
#: (Passing an empty text is NOT a way to clear a draft: the platform shows a
#: "Thinking…" placeholder for it.)
DRAFT_TEXT_LIMIT = 4096

#: Deliberately not ``TELEGRAM_UPDATE_INTERVAL`` (1.5 s), which exists because
#: editing a delivered message runs into Telegram's edit flood limits — a draft
#: is not a message and not an edit, it is the endpoint the platform built for
#: streaming, which is the entire reason to prefer it. So: its own value, moved
#: only against Telegram's own behaviour.
_DRAFT_UPDATE_INTERVAL = 0.2


def clip_draft(text: str, limit: int) -> str:
    """Fit a snapshot to the draft cap (counted in UTF-16 units, as the platform
    counts), clipping the answer before the status block so the header stays
    visible on a long reply."""
    return clip_snapshot_utf16(text, limit)


def _entity_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draft_markdown(snapshot: str) -> str:
    """A live snapshot as a rich draft (spec channels/telegram "Show the working
    status in a direct chat's thinking block"): the status header goes in the
    draft-only ``<tg-thinking>`` block, the narration and step lines follow as a
    list, and the answer written so far is rich markdown under them."""
    block, answer = split_snapshot(snapshot)
    header, *rest = block.split("\n")
    parts = [f"<tg-thinking>{_entity_escape(header.removeprefix('⏳ ').strip())}</tg-thinking>"]
    if rest:
        parts.append("\n".join(f"- {_entity_escape(line)}" for line in rest if line.strip()))
    if answer:
        parts.append(normalize_rich_markdown(answer))
    return "\n\n".join(parts)


def new_draft_id() -> int:
    """A draft identifier unique within this chat for the life of the turn.

    Telegram wants an Integer and scopes it per chat; a random 31-bit value is
    collision-free in practice and, unlike a counter, cannot repeat across a
    daemon restart while an old draft is still alive in someone's client.
    """
    return secrets.randbits(31)


class TelegramDraftLiveText(LiveTextSurface):
    """A live reply carried by ``sendMessageDraft``.

    Shares the throttle and dead-latch rules of every live surface. What it does
    NOT share is cleanup: the edit-based surface had to delete the scaffolding
    message it sent, while a draft is not a message at all — closing the handle
    just stops refreshing it, and the platform drops it.
    """

    def __init__(
        self,
        call: Call,
        chat_id: str,
        *,
        channel: str,
        feature: Feature,
        thread_id: str = "",
        now: Callable[[], float] | None = None,
        rich: Feature | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "keepalive_seconds": LIVE_KEEPALIVE_SECONDS,
            "min_interval": _DRAFT_UPDATE_INTERVAL,
        }
        if now is not None:
            kwargs["now"] = now
        super().__init__(**kwargs)
        self._call = call
        self._chat_id = chat_id
        self._channel = channel
        self._feature = feature
        # sendRichMessageDraft, where the server still offers it; None or
        # latched off sends the plain draft.
        self._rich = rich
        self._thread_id = thread_id
        self._draft_id = new_draft_id()

    @property
    def draft_id(self) -> int:
        return self._draft_id

    async def _write(self, text: str) -> None:
        text = clip_draft(text, DRAFT_TEXT_LIMIT)
        if self._rich is not None and self._rich.available:
            try:
                await self._call(
                    "sendRichMessageDraft",
                    rich_message={"markdown": draft_markdown(text)},
                    **self._common(),
                )
                return
            except Exception as e:
                # A server that does not know it latches the rich draft off and
                # this snapshot goes out as the plain draft instead; any other
                # refusal is this surface's failure, as for the plain draft.
                self._rich.note_failure(self._channel, e)
                if not is_unsupported(e):
                    raise
        await self._plain(text)

    def _common(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "chat_id": int(self._chat_id),
            "draft_id": self._draft_id,
            # Let the platform draw the stop control. Only safe to advertise
            # because the stopped_message_generation update is routed to the
            # same interrupt path /stop takes.
            "can_stop": True,
            # The finished reply is sent as a real message straight after, so a
            # kept draft would leave the user reading the answer twice.
            "keep_on_stop": False,
        }
        if self._thread_id:
            params["message_thread_id"] = int(self._thread_id)
        return params

    async def _plain(self, text: str) -> None:
        params = {**self._common(), "text": text}
        try:
            await self._call("sendMessageDraft", **params)
        except Exception as e:
            # An older Bot API server has never heard of this; latch it off so
            # the next turn opens the edit-based surface instead of paying for
            # a doomed round trip.
            self._feature.note_failure(self._channel, e)
            raise

    async def _finish(self, text: str) -> str:
        """A draft is a preview, not the reply: hand the whole text back so the
        caller sends it rendered and chunked through the ordinary path.

        Nothing is deleted — an unfinished draft expires on its own, which is
        exactly the cleanup the edit-based surface had to do by hand.
        """
        return text
