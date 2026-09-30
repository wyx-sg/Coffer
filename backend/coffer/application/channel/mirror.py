"""``ChannelMirror`` — a reply typed on the web also reaches the channel chat
the conversation came from (spec chat "Mirror a web reply into the channel it
came from").

Satisfies the chat kind's ``ChannelMirrorPort``. A reply goes to the chat at
once, prefixed ``(from Coffer)``, and its turn is queued with the same render
sink a channel-driven turn gets, so the answer lands in the chat as usual. When
the chat cannot be written to right now — the channel is not running, the send
raised, or earlier messages are still owed (order) — the reply waits in
``channel_outbox`` and the turn's answer is collected there behind it; the
runtime's tick hands each running channel to ``flush``, which delivers the rows
oldest first.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from coffer.application.channel.mirror_target import (
    FROM_COFFER,
    MirrorTarget,
    resolve_target,
)
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import (
    ChannelOutboxRepoPort,
    ChannelPeerRepoPort,
    ChannelThreadConversationRepoPort,
    ChannelThreadLocation,
)
from coffer.application.channel.turn_driver import QueuedInbound
from coffer.domain.chat.events import TextDelta, TurnDone, TurnError
from coffer.domain.chat.mirror import (
    ChannelPlaceView,
    MirrorResult,
    MirrorView,
    UndeliveredReply,
)

if TYPE_CHECKING:
    from coffer.application.channel.inbound import InboundProcessor
    from coffer.application.resource_service import ResourceService

__all__ = ["FLUSH_BACKOFF_SECONDS", "ChannelMirror"]

_logger = logging.getLogger(__name__)

#: After a failed delivery a channel's outbox is not tried again for this long,
#: so a platform that is refusing messages is not hammered every tick.
FLUSH_BACKOFF_SECONDS = 30.0

Sink = Callable[[asyncio.Queue[Any]], None]


class ChannelMirror:
    """Mirrors web replies into their channel chat; delivers what it owes."""

    def __init__(
        self,
        *,
        resources: ResourceService,
        threads: ChannelThreadConversationRepoPort,
        peers: ChannelPeerRepoPort,
        outbox: ChannelOutboxRepoPort,
        processor: InboundProcessor,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resources = resources
        self._threads = threads
        self._peers = peers
        self._outbox = outbox
        self._processor = processor
        self._clock = clock
        self._failed_at: dict[str, float] = {}
        # Collector tasks, held so they are not garbage-collected mid-turn.
        self._collectors: set[asyncio.Task[None]] = set()

    async def _target(self, conversation_id: str, channel_uid: str) -> MirrorTarget:
        return await resolve_target(self._resources, self._threads, conversation_id, channel_uid)

    async def describe(self, conversation_id: str, channel_uid: str) -> MirrorView:
        target = await self._target(conversation_id, channel_uid)
        owed = await self._outbox.pending_for_conversation(conversation_id)
        return MirrorView(
            deliverable=target.deliverable,
            platform=target.platform,
            channel=target.resource.name if target.resource is not None else None,
            target=target.target,
            reason=target.reason,
            undelivered=tuple(
                UndeliveredReply(kind=e.kind, text=e.text, created_at=e.created_at) for e in owed
            ),
        )

    async def places(self, conversation_ids: Sequence[str]) -> Mapping[str, ChannelPlaceView]:
        """One read for the whole page (``locate_many``). ``chat_name`` stays
        ``None``: Coffer keeps no group title — a group's peer row names the
        owner who paired it, not the group."""
        located = await self._threads.locate_many(conversation_ids)
        return {
            conversation_id: ChannelPlaceView(
                chat_kind=loc.chat_kind if loc.chat_kind in ("direct", "group") else None,
                thread=loc.thread_id != "",
                parallel_mark=row.parallel_mark if row is not None else None,
            )
            for conversation_id, (loc, row) in located.items()
        }

    async def mirror(self, conversation_id: str, channel_uid: str, text: str) -> MirrorResult:
        target = await self._target(conversation_id, channel_uid)
        loc = target.location
        if target.resource is None or loc is None or loc.chat_kind is None:
            return MirrorResult("kept", None)
        resource = target.resource
        body = FROM_COFFER + text
        binding = self._processor.binding(resource.name)
        peer = await self._peers.get_by_chat(resource.uid, loc.chat_id)
        owed = await self._outbox.pending_for_conversation(conversation_id)
        if binding is not None and peer is not None and not owed:
            try:
                await binding.adapter.send_text(
                    loc.chat_id, body, thread_id=loc.thread_id, chat_kind=loc.chat_kind
                )
            except Exception:
                _logger.warning(
                    "channel.mirror.send_failed",
                    extra={"channel": resource.name},
                    exc_info=True,
                )
            else:
                item = QueuedInbound(
                    text="",
                    thread_id=loc.thread_id,
                    chat_kind=loc.chat_kind,
                    conversation_thread_id=loc.thread_id,
                )
                sink = self._processor.turn_driver.render_sink(binding, peer, item, conversation_id)
                return MirrorResult("sent", sink)
        await self._outbox.add(
            resource_uid=resource.uid,
            chat_id=loc.chat_id,
            thread_id=loc.thread_id,
            chat_kind=loc.chat_kind,
            conversation_id=conversation_id,
            kind="reply",
            text=body,
        )
        return MirrorResult("pending", self._collector(conversation_id, loc))

    def _collector(self, conversation_id: str, loc: ChannelThreadLocation) -> Sink:
        """An ``on_start`` sink that keeps the turn's answer in the outbox, behind
        the reply that asked for it."""

        def on_start(queue: asyncio.Queue[Any]) -> None:
            task = asyncio.create_task(
                self._collect(conversation_id, loc, queue),
                name=f"channel-mirror-collect:{conversation_id}",
            )
            self._collectors.add(task)
            task.add_done_callback(self._collectors.discard)

        return on_start

    async def _collect(
        self, conversation_id: str, loc: ChannelThreadLocation, queue: asyncio.Queue[Any]
    ) -> None:
        parts: list[str] = []
        while True:
            event = await queue.get()
            if isinstance(event, TextDelta):
                parts.append(event.text)
            if event is None or isinstance(event, TurnDone | TurnError):
                break
        answer = "".join(parts).strip()
        if not answer:
            return
        try:
            await self._outbox.add(
                resource_uid=loc.resource_uid,
                chat_id=loc.chat_id,
                thread_id=loc.thread_id,
                chat_kind=loc.chat_kind or "direct",
                conversation_id=conversation_id,
                kind="answer",
                text=answer,
            )
        except Exception:
            _logger.exception("channel.mirror.collect_failed")

    async def flush(self, binding: ChannelBinding) -> None:
        """Deliver a running channel's owed messages, oldest first, stopping at
        the first one the platform refuses (the rest keep their order)."""
        resource_uid = binding.resource.uid
        failed = self._failed_at.get(resource_uid)
        if failed is not None and self._clock() - failed < FLUSH_BACKOFF_SECONDS:
            return
        for entry in await self._outbox.pending(resource_uid):
            if await self._peers.get_by_chat(resource_uid, entry.chat_id) is None:
                # The chat was un-paired since: Coffer owes it nothing it may send,
                # and the reply stays listed as undelivered rather than being
                # pushed into a chat that no longer belongs to the owner.
                continue
            try:
                await binding.adapter.send_text(
                    entry.chat_id,
                    entry.text,
                    thread_id=entry.thread_id,
                    chat_kind=entry.chat_kind,
                )
            except Exception:
                self._failed_at[resource_uid] = self._clock()
                _logger.warning(
                    "channel.mirror.flush_failed",
                    extra={"channel": binding.resource.name},
                    exc_info=True,
                )
                return
            await self._outbox.mark_delivered(entry.id)
        self._failed_at.pop(resource_uid, None)
