"""The ports the scheduled-task core needs, satisfied at the composition root.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from coffer.domain.channel.scheduled_run import ScheduledRun

__all__ = ["ScheduledRunRepoPort", "SessionTail", "SessionTailPort"]


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

    async def delete_for_channel(self, channel_uid: str) -> None: ...


@dataclass(frozen=True)
class SessionTail:
    """The end of one agent session, read from the agent's own record: the last
    message a person sent into it and the last reply it gave. Either is ``""``
    when the session has none or could not be read."""

    asked: str
    answered: str


class SessionTailPort(Protocol):
    """Reads the end of an agent's own session (spec channels "Write the daily
    report from the day's channel conversations"). Coffer keeps no copy of a
    conversation, so the daily report reads it where the agent keeps it."""

    async def tail(self, agent_key: str, session_id: str, cwd: str | None) -> SessionTail: ...
