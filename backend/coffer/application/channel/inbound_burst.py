"""Hold a burst of inbound messages and release it as one turn (spec channels
"Take a burst of messages as one turn").

A person rarely says everything in one message: they forward a chat record and
then type "look into this", or send a question and a correction right behind
it. Each message is held per ``(channel, chat, thread)`` for a short quiet
window; a message arriving inside the window joins the burst and restarts it,
and when the chat goes quiet the burst is released as ONE ``QueuedInbound``.

The window depends on what arrived last and is the channel's own setting: a text
message is usually the whole ask (``wait_after_text_seconds``), while a forwarded
record or files without text rarely are (``wait_after_forward_seconds``).
Platform-independent — the album buffer of spec channels/telegram
"Debounce an album into one turn" runs before this, inside the transport.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.turn_driver import QueuedInbound
from coffer.application.runtime.supervisor import spawn
from coffer.domain.channel.envelopes import InboundMessage
from coffer.domain.chat.attachment import Attachment

__all__ = [
    "MAX_WINDOW_SECONDS",
    "BurstKey",
    "BurstPart",
    "InboundBurst",
    "merge_parts",
    "window_for",
]

_logger = logging.getLogger(__name__)

#: The longest any window is held, whatever the config says — the config's own
#: bound, restated where the timer is armed.
MAX_WINDOW_SECONDS = 60.0

#: ``(channel, chat_id, thread_id)`` — the reply thread, not the conversation
#: key: two threads that share a conversation still never merge into one turn.
BurstKey = tuple[str, str, str]


@dataclass(frozen=True)
class BurstPart:
    """One held message, its origin block kept apart from its body so the
    released turn carries a single origin instead of one per message."""

    origin: str
    body: str
    item: QueuedInbound
    #: How long the chat must stay quiet after this message (see ``window_for``).
    window: float = 0.0


def window_for(binding: ChannelBinding, msg: InboundMessage) -> float:
    """The quiet window after ``msg``: the longer one for a forwarded record or
    files with no text of their own, which are rarely the whole ask."""
    if msg.forwarded or not msg.text.strip():
        return binding.wait_after_forward_seconds
    return binding.wait_after_text_seconds


#: ``(context, merged) -> awaitable`` — submits the released turn. ``context``
#: is whatever the caller handed ``add`` with the burst's latest message.
FlushCallback = Callable[[Any, QueuedInbound], Awaitable[None]]


@dataclass
class _Burst:
    context: Any
    parts: list[BurstPart] = field(default_factory=list)


def merge_parts(parts: list[BurstPart]) -> QueuedInbound:
    """Fold a burst into one turn: the last message's origin (it is what the
    reply attaches to and mentions), every body in arrival order, every
    attachment, and the first title hint the person actually wrote."""
    last = parts[-1]
    bodies = "\n\n".join(p.body for p in parts if p.body)
    attachments: tuple[Attachment, ...] = tuple(a for p in parts for a in p.item.attachments)
    title_hint = next((p.item.title_hint for p in parts if p.item.title_hint), "")
    return QueuedInbound(
        text=f"{last.origin}\n\n{bodies}" if bodies else last.origin,
        attachments=attachments,
        thread_id=last.item.thread_id,
        conversation_thread_id=last.item.conversation_thread_id,
        chat_kind=last.item.chat_kind,
        reply_to_message_id=last.item.reply_to_message_id,
        mention_user_id=last.item.mention_user_id,
        mention_user_email=last.item.mention_user_email,
        mention_user_name=last.item.mention_user_name,
        title_hint=title_hint,
    )


class InboundBurst:
    """Per-key quiet-window buffer. ``add`` holds a message and (re)arms the
    key's timer; ``flush`` releases a key now (a command arriving behind held
    messages); ``drop`` discards it (``/stop``); ``cancel_all`` on shutdown."""

    def __init__(
        self,
        on_flush: FlushCallback,
    ) -> None:
        self._on_flush = on_flush
        self._bursts: dict[BurstKey, _Burst] = {}
        self._timers: dict[BurstKey, asyncio.TimerHandle] = {}
        #: The latest release of each key still being submitted.
        self._releasing: dict[BurstKey, asyncio.Task[None]] = {}

    def add(self, key: BurstKey, context: Any, part: BurstPart) -> None:
        burst = self._bursts.get(key)
        if burst is None:
            burst = self._bursts[key] = _Burst(context=context)
        burst.context = context
        burst.parts.append(part)
        self._cancel_timer(key)
        window = max(0.0, min(part.window, MAX_WINDOW_SECONDS))
        self._timers[key] = asyncio.get_running_loop().call_later(window, self._fire, key)

    def holding(self, key: BurstKey) -> bool:
        return key in self._bursts

    async def flush(self, key: BurstKey) -> None:
        """Release ``key``'s burst now, and return only once it — and any release
        of this key already under way — has been submitted, so whatever the caller
        does next (a command) lands behind it."""
        self._cancel_timer(key)
        burst = self._bursts.pop(key, None)
        await self._wait_released(key)
        if burst is not None:
            await self._on_flush(burst.context, merge_parts(burst.parts))

    async def drop(self, key: BurstKey) -> None:
        """Discard what ``key`` holds (``/stop``). A release already under way is
        waited for, not raced: it was heard before the stop, so it reaches the
        queue first and the stop's pause holds it there."""
        self._cancel_timer(key)
        self._bursts.pop(key, None)
        await self._wait_released(key)

    async def settled(self) -> None:
        """Return once nothing is held and no release is still being submitted."""
        while self._bursts or self._releasing:
            await asyncio.sleep(0.005)

    def drop_channel(self, channel: str) -> None:
        for key in [k for k in self._bursts if k[0] == channel]:
            self._cancel_timer(key)
            self._bursts.pop(key, None)

    def cancel_all(self) -> None:
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        self._bursts.clear()
        for task in list(self._releasing.values()):
            task.cancel()
        self._releasing.clear()

    def _cancel_timer(self, key: BurstKey) -> None:
        timer = self._timers.pop(key, None)
        if timer is not None:
            timer.cancel()

    async def _wait_released(self, key: BurstKey) -> None:
        task = self._releasing.get(key)
        if task is not None:
            await asyncio.wait({task})

    def _fire(self, key: BurstKey) -> None:
        self._timers.pop(key, None)
        burst = self._bursts.pop(key, None)
        if burst is None:
            return
        # Chained behind this key's previous release, so two bursts of one chat
        # reach the conversation in the order they were released.
        previous = self._releasing.get(key)

        async def release() -> None:
            if previous is not None:
                await asyncio.wait({previous})
            await self._on_flush(burst.context, merge_parts(burst.parts))

        task = spawn(release(), name=f"channel-burst:{key}")
        self._releasing[key] = task
        task.add_done_callback(lambda t: self._reap(key, t))

    def _reap(self, key: BurstKey, task: asyncio.Task[None]) -> None:
        if self._releasing.get(key) is task:
            del self._releasing[key]
        with contextlib.suppress(asyncio.CancelledError):
            if task.exception() is not None:
                # The flush callback reports its own failures into the chat; a
                # raise here means that reporting itself broke — log, never lose.
                _logger.error("channel.burst.flush_failed", exc_info=task.exception())
