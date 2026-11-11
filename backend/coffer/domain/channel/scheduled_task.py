"""What a scheduled task is: a prompt Coffer sends an agent by itself at the
times it names (spec channels "Keep scheduled tasks as machine-local resources").

A task says three things — when it runs (:mod:`schedule`), what the agent is
told, and the agent, model and directory every run opens a new conversation
with. What the agent is told is a file, ``PROMPT.md`` in the task's own folder
(ADR automation-is-a-scheduled-prompt), so it is read and edited like any
other file; this config holds the rest. That is the whole mechanism; what a
task does with a chat, a report or a flow is its prompt's.

The task's file is ``Resource.config`` of a ``scheduled_task`` resource, filed
under ``local/``: its agent and directory are this machine's, and two machines
that both held it would both run it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from coffer.domain.channel.schedule import (
    MIN_REPEAT,
    OnceSchedule,
    Schedule,
    is_repeating,
    zone_of,
)

__all__ = [
    "PROMPT_FILE",
    "PROMPT_MAX_LENGTH",
    "ScheduledTaskConfig",
    "clean_prompt",
    "grace_for",
    "is_retired_follow_up",
    "min_repeat_ok",
]

#: The longest prompt a task keeps. It rides on every run.
PROMPT_MAX_LENGTH = 8000

#: The file in a task's folder that holds its prompt.
PROMPT_FILE = "PROMPT.md"


def clean_prompt(value: str) -> str:
    """A prompt as it is kept: trimmed, not empty, within :data:`PROMPT_MAX_LENGTH`."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("prompt must not be empty")
    if len(stripped) > PROMPT_MAX_LENGTH:
        raise ValueError(f"prompt is longer than {PROMPT_MAX_LENGTH} characters")
    return stripped


#: Fields a task file written before 2026-11-06 may still carry: the chat it
#: ran in, how it opened its conversation there, whom it mentioned, the daily
#: report's material and template, and the follow-up's origin and chain.
_RETIRED = (
    "chat",
    "session",
    "mention",
    "material",
    "template",
    "origin",
    "chain_started_at",
    "chain_index",
)


def is_retired_follow_up(raw: Any) -> bool:
    """Whether a task file is a follow-up an agent booked before follow-ups
    were removed (2026-11-06): it has no meaning without its chat."""
    return isinstance(raw, dict) and raw.get("origin") == "agent"


def _upgrade(raw: Any) -> Any:
    """A task file from before tasks lost their chat (2026-11-06), read as one
    now: the retired fields go, a task that named no agent runs on Claude Code,
    and a ``weekdays`` schedule becomes the cron it meant. Every file of that
    time carries ``session``, so a new write never passes through here."""
    if not isinstance(raw, dict) or "session" not in raw:
        return raw
    data = {k: v for k, v in raw.items() if k not in _RETIRED}
    data["agent"] = data.get("agent") or "claude_code"
    schedule = data.get("schedule")
    if isinstance(schedule, dict) and schedule.get("kind") == "weekdays":
        hour, minute = str(schedule.get("time", "09:00")).split(":", 1)
        rest = {k: v for k, v in schedule.items() if k not in ("kind", "time")}
        data["schedule"] = rest | {"kind": "cron", "expr": f"{int(minute)} {int(hour)} * * 1-5"}
    return data


class ScheduledTaskConfig(BaseModel):
    """``Resource.config`` of a ``scheduled_task``."""

    model_config = ConfigDict(extra="forbid")

    schedule: Schedule
    #: The agent (its key, ``claude_code`` or ``codex`` — one agent per type),
    #: model and directory every run opens a new conversation with. No model
    #: is the agent's default; no directory is the task's own folder.
    agent: str = Field(min_length=1)
    model: str | None = None
    cwd: str | None = None
    #: A run missed while this Mac slept or Coffer was stopped runs once on
    #: return while it is still within its grace; off skips it.
    catch_up: bool = True

    @model_validator(mode="before")
    @classmethod
    def _old_file(cls, raw: Any) -> Any:
        # The prompt is the task's PROMPT.md, never part of its config; it is
        # refused here with that reason rather than as an unknown field. A file
        # written before 2026-11-11 carries one: it is moved into PROMPT.md at
        # startup, before the file is read as a task.
        if isinstance(raw, dict) and raw.get("prompt") is not None:
            raise ValueError(f"a task's prompt is its {PROMPT_FILE}, not part of its config")
        if isinstance(raw, dict):
            raw = {k: v for k, v in raw.items() if k != "prompt"}
        return _upgrade(raw)


def min_repeat_ok(schedule: Schedule, gap: timedelta | None) -> bool:
    """Whether a repeating schedule's shortest gap respects :data:`MIN_REPEAT`."""
    return not is_repeating(schedule) or gap is None or gap >= MIN_REPEAT


def grace_for(config: ScheduledTaskConfig, *, slot: datetime, created_at: datetime) -> timedelta:
    """How late a missed slot may still run (spec channels "Catch up a missed
    run once, within its grace").

    A one-off waited ``slot - created_at``; it may run up to half that late,
    no less than 15 minutes and no more than 2 hours — a one-off is worth
    something only while it is timely. A repeating slot may run until the end
    of its own day on the schedule's wall clock; after that the next slot is the one that counts.
    """
    if isinstance(config.schedule, OnceSchedule):
        half = (slot - created_at) / 2
        return max(timedelta(minutes=15), min(timedelta(hours=2), half))
    zone = config.schedule.timezone
    local = slot.astimezone(zone_of(zone)) if zone else slot.astimezone()
    end_of_day = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return end_of_day - local
