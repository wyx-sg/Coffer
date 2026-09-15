"""Process-global per-conversation turn state (spec channels FR-050, FR-053).

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
from collections.abc import Callable
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
    """One message waiting for its turn (FR-050).

    ``text`` is what the turn commits as the user message; ``attachments`` and
    ``title_hint`` are what a channel adds to it (FR-033, FR-048); ``on_start``
    is how a channel gets its renderer attached to the turn the moment it
    begins. A web message carries only its text.
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
    interrupted: bool = field(default=False)


@dataclass
class TurnState:
    """Everything the orchestrator holds for one conversation."""

    bus: ConversationBus = field(default_factory=ConversationBus)
    active: ActiveTurn | None = None
    queue: list[PendingMessage] = field(default_factory=list)
    # Set by an interrupt; blocks auto-advance until the owner resumes (any
    # ``enqueue_message`` / ``set_pending`` clears it) — FR-051.
    paused: bool = False

    @property
    def idle(self) -> bool:
        """Nothing in flight, nothing waiting, nobody watching."""
        return self.active is None and not self.queue and self.bus.subscriber_count == 0


# conversation_id → state. Mutated in place (never re-bound) so importers share it.
_STATES: dict[str, TurnState] = {}


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
    _STATES.clear()
