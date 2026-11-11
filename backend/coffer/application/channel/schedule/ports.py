"""The ports the scheduled-task core needs, satisfied at the composition root.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol

from coffer.domain.channel.scheduled_run import RunOutcome, ScheduledRun

__all__ = ["FreshTurnPort", "ScheduledRunRepoPort"]


class FreshTurnPort(Protocol):
    """Starts a run's turn (spec channels "Run a scheduled task in a fresh
    conversation of its own"): a new conversation
    on ``agent``, in ``cwd`` (the Coffer workspace when ``None``), on ``model`` (the
    agent's default when ``None``), titled ``title``, whose one turn is given
    ``text``. Returns the conversation's id once the turn is under way;
    ``on_end`` is told how it ended. Raises ``CofferError`` when the
    conversation cannot be opened or the turn cannot start."""

    async def start(
        self,
        *,
        agent: str,
        model: str | None,
        cwd: str | None,
        title: str,
        text: str,
        on_end: Callable[[RunOutcome, str], Awaitable[None]],
    ) -> str: ...


class ScheduledRunRepoPort(Protocol):
    """Every run of every task (``scheduled_task_runs`` in ``runs.db``)."""

    async def add(self, run: ScheduledRun) -> None: ...

    async def finish(
        self,
        run_id: str,
        *,
        outcome: str,
        reason: str,
        finished_at: datetime,
        conversation_id: str | None = None,
    ) -> None: ...

    async def note_conversation(self, run_id: str, conversation_id: str) -> None: ...

    async def get(self, run_id: str) -> ScheduledRun | None: ...

    async def latest_slot(self, task_uid: str) -> datetime | None: ...

    async def for_task(self, task_uid: str, *, limit: int = 50) -> list[ScheduledRun]: ...

    async def latest_for(self, task_uids: Sequence[str]) -> dict[str, ScheduledRun]: ...

    async def since(self, when: datetime) -> list[ScheduledRun]: ...

    async def close_interrupted(self, *, reason: str, finished_at: datetime) -> int: ...
