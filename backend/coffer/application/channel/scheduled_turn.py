"""What the turn driver carries for a turn a scheduled task started, and how
such a turn's ending is reported back.

A scheduled run enters a chat exactly as a message does — the same turn driver,
the same renderer, the same queue (ADR
scheduled-tasks-are-turns-coffer-starts-in-a-chat). Two things differ, and they
ride here: a reply that opens with ``[SILENT]`` is not sent (spec channels
"Stay silent when a scheduled run has nothing to say"), and the run's history
row is told how the turn ended.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from coffer.domain.channel.scheduled_run import RunOutcome

__all__ = ["ScheduledTurn", "run_outcome"]

#: Told how the run's turn ended: the outcome and, for a failure, why.
OnEnd = Callable[[RunOutcome, str], Awaitable[None]]


@dataclass(frozen=True)
class ScheduledTurn:
    task_uid: str
    run_id: str
    #: A repeating task: its runs book no follow-ups of their own.
    repeats: bool
    on_end: OnEnd
    chain_started_at: datetime | None = None
    chain_index: int = 0


def run_outcome(turn_outcome: str, *, silenced: bool) -> RunOutcome:
    """A rendered turn's outcome (``done`` / ``failed`` / ``stopped``) as the
    run's."""
    if turn_outcome == "failed":
        return "failed"
    if turn_outcome == "stopped":
        return "stopped"
    return "silent" if silenced else "replied"
