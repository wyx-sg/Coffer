"""Process-global per-conversation turn state (spec chat "Queue messages sent during a
turn", "Release turn state nobody needs").

Single-daemon by design: everything the orchestrator holds for one conversation
— the live-event bus, the in-flight turn, the pending queue and its pause flag —
lives in ONE :class:`TurnState` per conversation, in one module-level dict.
Shared by the ``TurnOrchestrator`` and the detached turn task (``turn_runner``);
kept in its own module so the two can both reference it without an import
cycle.

A state exists only while something needs it: a turn in flight, a message
waiting, or a subscriber attached. :func:`evict_if_idle` releases the rest, so a
daemon that has served ten thousand conversations does not carry ten thousand
buses.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from coffer.application.chat.bus import ConversationBus
from coffer.domain.chat.attachment import Attachment
from coffer.domain.chat.events import AgentEvent

#: What a channel-driven message is handed when its turn starts: the dedicated
#: event queue (ending in ``None``) its renderer drains. Web messages have none —
#: the web observes via the bus.
TurnSink = Callable[["asyncio.Queue[AgentEvent | None]"], None]


@dataclass(frozen=True)
class PendingMessage:
    """One message waiting for its turn (spec chat "Queue messages sent during a turn").

    ``text`` is what the turn commits as the user message; ``attachments`` and
    ``title_hint`` are what a channel adds to it (spec channels "Persist inbound
    attachments as references", spec chat "Persist conversations and messages in
    SQLite"); ``on_start`` is how a channel gets its renderer attached to the turn the
    moment it begins. A web message carries only its text.
    """

    text: str
    attachments: tuple[Attachment, ...] = ()
    title_hint: str | None = None
    on_start: TurnSink | None = None


@dataclass
class ActiveTurn:
    """In-process record of one conversation's in-flight turn."""

    bus: ConversationBus
    # A dedicated event queue for a channel-driven turn (see ``PendingMessage``);
    # ``None`` for a web turn, which observes via the bus instead. When present
    # it receives every event plus a ``None`` end-of-stream sentinel.
    primary_queue: asyncio.Queue[AgentEvent | None] | None = None
    task: asyncio.Task[None] | None = None
    # Why the task was cancelled, set by whoever cancels it: ``interrupted`` (the
    # user stopped it — keep the partial, complete) or ``discarded`` (the
    # conversation is being deleted — throw the turn away). A cancellation with
    # neither is the daemon going down: the partial is kept, marked failed.
    interrupted: bool = field(default=False)
    discarded: bool = field(default=False)


@dataclass
class TurnState:
    """Everything the orchestrator holds for one conversation."""

    bus: ConversationBus = field(default_factory=ConversationBus)
    active: ActiveTurn | None = None
    queue: list[PendingMessage] = field(default_factory=list)
    # Set by an interrupt; blocks auto-advance until the owner resumes (any
    # ``enqueue_message`` / ``set_pending`` clears it) — spec chat "Pause the pending
    # queue on interrupt".
    paused: bool = False

    @property
    def idle(self) -> bool:
        """Nothing in flight, nothing waiting, nobody watching."""
        return self.active is None and not self.queue and self.bus.subscriber_count == 0


# conversation_id → state. Mutated in place (never re-bound) so importers share it.
_STATES: dict[str, TurnState] = {}


def reconcile_queue(queue: list[PendingMessage], texts: Sequence[str]) -> list[PendingMessage]:
    """The queue ``texts`` describes, reusing an existing entry for each text it
    still contains (first unused match wins) so a reordered or partly-dropped
    queue keeps every message's attachments and renderer."""
    unused = list(queue)
    result: list[PendingMessage] = []
    for text in texts:
        match = next((m for m in unused if m.text == text), None)
        if match is not None:
            unused.remove(match)
            result.append(match)
        else:
            result.append(PendingMessage(text=text))
    return result


def state_for(conversation_id: str) -> TurnState:
    """The conversation's state, created on first use."""
    state = _STATES.get(conversation_id)
    if state is None:
        state = TurnState()
        _STATES[conversation_id] = state
    return state


def peek(conversation_id: str) -> TurnState | None:
    """The conversation's state if it has one; never creates."""
    return _STATES.get(conversation_id)


def release_active(conversation_id: str, active: ActiveTurn) -> None:
    """Ownership-checked release of the in-flight slot: only ``active`` itself is
    evicted, so a racing start that registered a fresh turn is not lost."""
    state = _STATES.get(conversation_id)
    if state is not None and state.active is active:
        state.active = None


def evict_if_idle(conversation_id: str) -> bool:
    """Drop the conversation's state when nothing needs it; ``True`` if dropped."""
    state = _STATES.get(conversation_id)
    if state is None or not state.idle:
        return False
    del _STATES[conversation_id]
    return True


def active_turns() -> dict[str, ActiveTurn]:
    """The in-flight turns by conversation (for testing/monitoring only)."""
    return {cid: st.active for cid, st in _STATES.items() if st.active is not None}


def held_conversations() -> set[str]:
    """Which conversations currently hold state (for testing/monitoring only)."""
    return set(_STATES)


def clear_active_turns() -> None:
    """Clear all per-conversation orchestrator state (test teardown only)."""
    global _stopping_loop
    _STATES.clear()
    _stopping_loop = None


class TurnsStopping(RuntimeError):  # noqa: N818
    """A turn start refused because the daemon is shutting down."""


# The event loop :func:`stop_all_turns` ran on; from then on no turn starts on
# it. Scoped to the loop rather than the process so an app started afresh on a
# new loop in the same process (tests, an in-process restart) is not refused.
_stopping_loop: asyncio.AbstractEventLoop | None = None


def is_stopping() -> bool:
    """Whether the daemon has begun stopping its turns (no new turn may start)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return _stopping_loop is loop


async def stop_all_turns(*, timeout: float = 5.0) -> int:
    """Stop every in-flight turn and wait for each to finish writing its partial.

    Called by the daemon's teardown before the database is disposed. First it
    closes the door: no turn starts after this (``is_stopping``) and every
    pending queue is paused, so a cancelled turn's end does not auto-advance
    into a fresh one mid-teardown. Queued messages stay queued; the queue is
    in-memory, so they go with the daemon, uncommitted (spec chat "Queue
    messages sent during a turn"). A turn cancelled this way is neither an
    interrupt nor a delete, so its runner keeps the partial reply and marks it
    failed (spec chat "Keep partial output when a turn is interrupted or
    fails").

    A start already underway when the door closed — its slot reserved, its
    task not yet spawned — is waited for too, and cancelled if it got as far
    as spawning. Waiting is bounded: whatever does not settle within
    ``timeout`` is left to the startup sweep. Returns how many turns were
    cancelled.
    """
    global _stopping_loop
    loop = asyncio.get_running_loop()
    _stopping_loop = loop
    for st in _STATES.values():
        st.paused = True
    deadline = loop.time() + timeout
    cancelled: set[asyncio.Task[None]] = set()
    while True:
        running: list[asyncio.Task[None]] = []
        starting = False
        for st in list(_STATES.values()):
            if st.active is None:
                continue
            if st.active.task is None:
                starting = True
            elif not st.active.task.done():
                running.append(st.active.task)
        for task in running:
            if task not in cancelled:
                task.cancel()
                cancelled.add(task)
        remaining = deadline - loop.time()
        if (not running and not starting) or remaining <= 0:
            return len(cancelled)
        if running:
            await asyncio.wait(running, timeout=remaining)
        else:
            await asyncio.sleep(min(0.01, remaining))
