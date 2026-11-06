"""One run of a scheduled task, as its history keeps it (spec channels "Keep
every scheduled run in the task's history").

A run is history, so it lives in ``runs.db`` beside the other run history,
and it outlives its task: a removed task's runs stay readable here. Ids,
times and outcomes only — never what the agent said, which stays in the
run's conversation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

__all__ = ["TERMINAL_OUTCOMES", "RunOutcome", "ScheduledRun"]

#: How a run ended. ``running`` while it is under way; ``done`` when its turn
#: finished (the answer stays in its conversation); ``skipped`` when it never
#: started (missed beyond its grace, the previous run still going); ``failed``
#: and ``stopped`` as for any turn.
RunOutcome = Literal["running", "done", "skipped", "failed", "stopped"]

TERMINAL_OUTCOMES: frozenset[str] = frozenset({"done", "skipped", "failed", "stopped"})


@dataclass(frozen=True)
class ScheduledRun:
    run_id: str
    task_uid: str
    #: The task's name when it ran: a removed task has no file to name it.
    task_name: str
    #: The slot the run was for, and whether it ran late for it (a catch-up).
    due_at: datetime
    catch_up: bool
    started_at: datetime
    outcome: RunOutcome
    #: Why it was skipped or failed, in a line a person reads; ``""`` otherwise.
    reason: str = ""
    finished_at: datetime | None = None
    conversation_id: str = ""
    #: ``schedule`` for a run its times started, ``manual`` for Run now.
    trigger: Literal["schedule", "manual"] = "schedule"
