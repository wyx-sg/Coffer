"""Closing the parallel threads nobody has used for a day (spec channels "Open
parallel conversations beside a direct chat").

`/thread` opens a parallel conversation beside a direct chat; `/close` inside it
closes it. Most are never closed by hand — the task is done and the person moves
on — so they would stay in `/status` for ever. The sweep closes each one that has
sat idle for :data:`IDLE_CLOSE_AFTER`, silently: nothing is sent to the chat,
and a later message in the thread is answered with the closed notice
(``parallel_threads.CLOSED_NOTICE``).

Idle means all three: no turn running on the thread's conversation, nothing
queued or held on it, and no activity for the whole window. Activity is the
later of the bound conversation's ``updated_at`` — bumped when each turn starts
and when it ends, the same signal "Open a new conversation after an idle period"
reads — and the thread row's own ``updated_at`` (when it was opened or last
rebound), which is all a thread whose conversation has gone has to go on.

Each pass is a handful of async SQLite reads over the open parallel threads, a
small set, so it runs on the event loop with nothing pushed to a thread. The loop
stops when its task is cancelled (``raise_if_stopping``).

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from coffer.application.channel.conversation_ops import ConversationPort
from coffer.application.channel.store_ports import (
    ChannelThreadConversation,
    ChannelThreadConversationRepoPort,
)
from coffer.application.channel.turn_driver import TurnPort
from coffer.application.runtime.cancellation import raise_if_stopping
from coffer.domain.chat.errors import ConversationNotFound

__all__ = ["IDLE_CLOSE_AFTER", "SWEEP_INTERVAL_S", "ParallelThreadSweep"]

_logger = logging.getLogger(__name__)

#: How long a parallel thread may sit idle before the sweep closes it. A day:
#: long enough that a thread left overnight mid-task is still there in the
#: morning, short enough that `/status` does not fill up with finished ones.
IDLE_CLOSE_AFTER = timedelta(hours=24)
#: How often the sweep looks. A thread is closed at most this long after its
#: idle window is up, which nobody notices at a day's window.
SWEEP_INTERVAL_S = 60 * 60.0


class ParallelThreadSweep:
    """Closes every open parallel thread idle for :data:`IDLE_CLOSE_AFTER`."""

    def __init__(
        self,
        *,
        threads: ChannelThreadConversationRepoPort,
        conversations: ConversationPort,
        turns: TurnPort,
        is_running: Callable[[str], bool],
        idle_after: timedelta = IDLE_CLOSE_AFTER,
        interval_s: float = SWEEP_INTERVAL_S,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._threads = threads
        self._conversations = conversations
        self._turns = turns
        #: Whether a turn is running on a conversation (the chat platform's own
        #: record, so a web-started turn counts too).
        self._is_running = is_running
        self._idle_after = idle_after
        self._interval_s = interval_s
        self._now = now

    async def run(self) -> None:
        """Sweep now, then every ``interval_s``, until the task is cancelled."""
        while True:
            try:
                await self.sweep_once()
            except Exception as exc:
                raise_if_stopping(exc)
                _logger.exception("channel.thread_sweep.failed")
            await asyncio.sleep(self._interval_s)

    async def sweep_once(self) -> int:
        """One pass; how many threads it closed."""
        closed = 0
        for row in await self._threads.open_parallel_threads():
            if await self._idle(row) and await self._threads.close_parallel(
                row.resource_uid, row.chat_id, row.thread_id
            ):
                closed += 1
        if closed:
            _logger.info("channel.thread_sweep.closed", extra={"closed": closed})
        return closed

    async def _idle(self, row: ChannelThreadConversation) -> bool:
        last = row.updated_at
        bound = row.active_conversation_id
        if bound is not None:
            if self._is_running(bound) or self._turns.pending(bound):
                return False
            try:
                conversation = await self._conversations.get_conversation(bound)
            except ConversationNotFound:
                conversation = None
            if conversation is not None:
                last = max(last, conversation.updated_at)
        return self._now() - last >= self._idle_after
