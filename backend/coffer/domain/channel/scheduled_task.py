"""What a scheduled task is: a prompt Coffer sends an agent by itself at the
times it names (spec scheduled-tasks "Keep scheduled tasks as machine-local resources").

A task says three things — when it runs (:mod:`schedule`), what the agent is
told, and the agent, model and folder every run opens a new conversation with
(the task's own folder unless it names another). What the agent is told is a
file, ``PROMPT.md`` in the task's own folder
(ADR automation-is-a-scheduled-prompt), so it is read and edited like any
other file; this config holds the rest. That is the whole mechanism; what a
task does with a chat, a report or a flow is its prompt's.

The task's file is ``Resource.config`` of a ``scheduled_task`` resource, filed
under ``local/``: its agent and folder are this machine's, and two machines
that both held it would both run it.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from coffer.domain.channel.schedule import MIN_REPEAT, Schedule, is_repeating

__all__ = [
    "CATCH_UP_WINDOW",
    "PROMPT_FILE",
    "ScheduledTaskConfig",
    "clean_prompt",
    "min_repeat_ok",
]

#: How late the most recent missed slot may still run (spec scheduled-tasks
#: "Catch up a missed run once, within seven days"). Whether late work still
#: makes sense is the agent's to judge: its message says when it was due.
CATCH_UP_WINDOW = timedelta(days=7)

#: The file in a task's folder that holds its prompt.
PROMPT_FILE = "PROMPT.md"


def clean_prompt(value: str) -> str:
    """A prompt as it is kept: trimmed and not empty."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("prompt must not be empty")
    return stripped


def _absolute(value: str | None) -> str | None:
    path = (value or "").strip()
    if not path:
        return None
    if not PurePosixPath(path).is_absolute():
        raise ValueError(f"a task's folder must be an absolute path, not {path!r}")
    return path


class ScheduledTaskConfig(BaseModel):
    """``Resource.config`` of a ``scheduled_task``."""

    model_config = ConfigDict(extra="forbid")

    schedule: Schedule
    #: The agent (its key, ``claude_code`` or ``codex`` — one agent per type)
    #: and model every run opens a new conversation with. No model is the
    #: agent's default.
    agent: str = Field(min_length=1)
    model: str | None = None
    #: The folder every run works in, as an absolute path on this machine;
    #: none is the task's own folder, where its ``PROMPT.md`` always is.
    cwd: str | None = None
    #: A run missed while this Mac slept or Coffer was stopped runs once on
    #: return, within :data:`CATCH_UP_WINDOW`; off skips it.
    catch_up: bool = True

    _cwd = field_validator("cwd")(_absolute)

    @model_validator(mode="before")
    @classmethod
    def _no_prompt(cls, raw: Any) -> Any:
        # The prompt is the task's PROMPT.md, never part of its config; it is
        # refused with that reason rather than as an unknown field.
        if isinstance(raw, dict) and raw.get("prompt") is not None:
            raise ValueError(f"a task's prompt is its {PROMPT_FILE}, not part of its config")
        return raw


def min_repeat_ok(schedule: Schedule, gap: timedelta | None) -> bool:
    """Whether a repeating schedule's shortest gap respects :data:`MIN_REPEAT`."""
    return not is_repeating(schedule) or gap is None or gap >= MIN_REPEAT
