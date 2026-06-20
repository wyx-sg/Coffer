"""Process-global per-conversation turn state (ADR-031).

Single-daemon by design: the in-flight turn, the live-event bus, and the pending
queue for each conversation live in module-level dicts. Shared by the
``TurnOrchestrator`` and the detached turn task (``turn_runner``); kept in its own
module so the two can both reference it without an import cycle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from coffer.application.chat.bus import ConversationBus
from coffer.domain.chat.events import AgentEvent


@dataclass
class _ActiveTurn:
    """In-process record of one conversation's in-flight turn."""

    bus: ConversationBus
    # A dedicated event queue for a ``start_turn`` caller (the channel renderer);
    # ``None`` for a web turn, which observes via the bus instead. When present it
    # receives every event plus a ``None`` end-of-stream sentinel.
    primary_queue: asyncio.Queue[AgentEvent | None] | None = None
    task: asyncio.Task[None] | None = None
    interrupted: bool = field(default=False)


@dataclass
class _PendingState:
    """A conversation's pending-message queue (ADR-031)."""

    queue: list[str] = field(default_factory=list)
    # Set by an interrupt; blocks auto-advance until the owner resumes (any
    # ``enqueue_message`` / ``set_pending`` clears it).
    paused: bool = False


# conversation_id → state. Mutated in place (never re-bound) so importers share it.
_ACTIVE_TURNS: dict[str, _ActiveTurn] = {}
_BUSES: dict[str, ConversationBus] = {}
_PENDING: dict[str, _PendingState] = {}


def active_turns() -> dict[str, _ActiveTurn]:
    """Expose the active-turns registry (for testing/monitoring only)."""
    return _ACTIVE_TURNS


def clear_active_turns() -> None:
    """Clear all per-conversation orchestrator state (test teardown only)."""
    _ACTIVE_TURNS.clear()
    _BUSES.clear()
    _PENDING.clear()
