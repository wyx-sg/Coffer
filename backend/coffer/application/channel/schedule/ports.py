"""The ports the scheduled-task core needs, satisfied at the composition root.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from coffer.domain.channel.scheduled_run import RunOutcome, ScheduledRun

__all__ = ["Anchor", "FreshTurnPort", "ScheduledRunRepoPort", "TaskAnchorPort", "TaskFolderPort"]


@dataclass(frozen=True)
class Anchor:
    """Where a switched-on task's slots are counted from."""

    #: The schedule the anchor was taken for, as JSON: another one counts afresh.
    schedule: str
    #: The last slot the scheduler settled, or the moment the task was switched
    #: on or given this schedule.
    at: datetime


class TaskAnchorPort(Protocol):
    """Each switched-on task's :class:`Anchor`, kept on this machine. A task
    has one only while it is on, so one resumed after a pause counts from its
    resume, not from the slots it was paused through."""

    def all(self) -> dict[str, Anchor]: ...

    def replace(self, anchors: dict[str, Anchor]) -> None: ...


class FreshTurnPort(Protocol):
    """Starts a run's turn (spec scheduled-tasks "Run a scheduled task in a fresh
    conversation of its own"): a new conversation
    on ``agent``, in ``cwd`` (the folder the task names, else its own), on ``model`` (the
    agent's default when ``None``), titled ``title``, whose one turn is given
    ``text``. Returns the conversation's id once the turn is under way;
    ``on_end`` is told how it ended. Raises ``CofferError`` when the
    conversation cannot be opened or the turn cannot start."""

    async def start(
        self,
        *,
        agent: str,
        model: str | None,
        cwd: str,
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

    async def for_task(self, task_uid: str, *, limit: int = 50) -> list[ScheduledRun]: ...

    async def latest_for(self, task_uids: Sequence[str]) -> dict[str, ScheduledRun]: ...

    async def close_interrupted(self, *, reason: str, finished_at: datetime) -> int: ...


class TaskFolderPort(Protocol):
    """Each task's own folder under Coffer's workspace
    (``scheduled-tasks/<uid>/``): its ``PROMPT.md``, and whatever its runs
    leave there."""

    def path(self, task_uid: str) -> str:
        """The folder's absolute path, created when absent."""
        ...

    def exists(self, path: str) -> bool:
        """Whether ``path``, a folder a task names for its runs, is there."""
        ...

    def read_prompt(self, task_uid: str) -> str | None:
        """The prompt, or ``None`` when the file is missing."""
        ...

    def write_prompt(self, task_uid: str, text: str) -> None: ...
