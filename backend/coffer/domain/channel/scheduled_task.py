"""What a scheduled task is: a turn Coffer starts by itself, in a chat, at the
times it names (spec channels "Keep scheduled tasks as machine-local resources").

A task says four things — when it runs (:mod:`schedule`), which chat it runs
in and whether it carries on that chat's conversation or opens a fresh one,
what the agent is told, and who set it up. A follow-up an agent books for
itself, the daily report and a task the owner writes are all the same thing
with different values; nothing downstream tells them apart except by those
values (ADR scheduled-tasks-are-turns-coffer-starts-in-a-chat).

The task's file is ``Resource.config`` of a ``scheduled_task`` resource, filed
under ``local/`` like the channel it names: its chat, agent and directory are
this machine's, and two machines that both held it would both run it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from coffer.domain.channel.schedule import (
    MIN_REPEAT,
    OnceSchedule,
    Schedule,
    is_repeating,
)

__all__ = [
    "CHAIN_MAX_RUNS",
    "CHAIN_MAX_SPAN",
    "FOLLOW_UPS_PER_THREAD",
    "FOLLOW_UP_MAX_AHEAD",
    "FOLLOW_UP_MIN_AHEAD",
    "MATERIAL_CHANNEL_DAY",
    "PROMPT_MAX_LENGTH",
    "SILENT_MARK",
    "TEMPLATE_DAILY_REPORT",
    "ScheduledTaskConfig",
    "TaskChat",
    "TaskMention",
    "grace_for",
    "min_repeat_ok",
]

#: A reply that opens with this is not sent (spec channels "Stay silent when a
#: scheduled run has nothing to say"). A failed run is always told.
SILENT_MARK = "[SILENT]"

#: The longest prompt a task keeps. It rides on every run.
PROMPT_MAX_LENGTH = 8000

#: The material a task may ask Coffer to fold in: the day's channel conversations.
MATERIAL_CHANNEL_DAY = "channel_day"

#: The template the Channels page's daily report is made from.
TEMPLATE_DAILY_REPORT = "daily_report"

#: Limits on what an agent books for itself (spec channels "Let an agent book a
#: follow-up in the thread it is answering"): how many may wait in one thread,
#: how soon and how far ahead, and how long a chain of follow-ups — one run
#: booking the next — may grow.
FOLLOW_UPS_PER_THREAD = 3
FOLLOW_UP_MIN_AHEAD = timedelta(minutes=5)
FOLLOW_UP_MAX_AHEAD = timedelta(days=7)
CHAIN_MAX_RUNS = 10
CHAIN_MAX_SPAN = timedelta(days=7)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskChat(_Model):
    """Where the task's turn runs and its reply goes: one chat of one channel.

    ``thread_id`` is where the reply is posted; ``conversation_thread_id`` is
    which of the chat's conversations it joins — the two differ for a casual
    reply-in-thread in a direct chat, exactly as for a message that arrived
    there (spec channels "Key conversation identity by channel, chat and thread").
    """

    channel: str = Field(min_length=1)
    chat_id: str = Field(min_length=1)
    chat_kind: Literal["direct", "group"] = "direct"
    thread_id: str = ""
    conversation_thread_id: str = ""


class TaskMention(_Model):
    """Whom a group reply opens by @mentioning — whoever asked for the follow-up."""

    user_id: str = ""
    email: str = ""
    name: str = ""


class ScheduledTaskConfig(_Model):
    """``Resource.config`` of a ``scheduled_task``."""

    schedule: Schedule
    prompt: str = Field(min_length=1, max_length=PROMPT_MAX_LENGTH)
    chat: TaskChat
    #: ``continue``: the run joins the chat's conversation, with its context.
    #: ``fresh``: every run opens a new conversation there.
    session: Literal["continue", "fresh"] = "fresh"
    #: For a fresh conversation only: the agent (its key, ``claude_code`` or
    #: ``codex`` — one agent per type), directory and model it opens with.
    #: Unset means the chat's own sticky choice, then the channel's.
    agent: str | None = None
    cwd: str | None = None
    model: str | None = None
    #: Who asked for it to be @mentioned when the run has something to say.
    mention: TaskMention | None = None
    #: What Coffer gathers and folds into the run's message.
    material: Literal["none", "channel_day"] = "none"
    #: ``owner``: set up by the owner (the page, the CLI, or asking in a chat).
    #: ``agent``: a follow-up the agent booked for itself.
    origin: Literal["owner", "agent"] = "owner"
    #: A follow-up chain: when its first follow-up was booked, and which link
    #: this one is (1 for the first).
    chain_started_at: datetime | None = None
    chain_index: int = Field(default=1, ge=1)
    #: A run missed while this Mac slept or Coffer was stopped runs once on
    #: return while it is still within its grace; off skips it.
    catch_up: bool = True
    #: The template the task was made from, ``""`` for none.
    template: Literal["", "daily_report"] = ""

    @field_validator("prompt")
    @classmethod
    def _prompt(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("prompt must not be empty")
        return stripped

    @model_validator(mode="after")
    def _consistent(self) -> ScheduledTaskConfig:
        if self.session == "continue" and (self.agent or self.cwd or self.model):
            raise ValueError(
                "agent, cwd and model apply to a fresh conversation only; "
                "a task that continues the chat's conversation runs on that conversation's"
            )
        if self.model and not self.agent:
            raise ValueError("a model belongs to an agent: name the agent too")
        if self.origin == "agent" and not isinstance(self.schedule, OnceSchedule):
            raise ValueError("a follow-up an agent books runs once")
        return self


def min_repeat_ok(schedule: Schedule, gap: timedelta | None) -> bool:
    """Whether a repeating schedule's shortest gap respects :data:`MIN_REPEAT`."""
    return not is_repeating(schedule) or gap is None or gap >= MIN_REPEAT


def grace_for(config: ScheduledTaskConfig, *, slot: datetime, created_at: datetime) -> timedelta:
    """How late a missed slot may still run (spec channels "Catch up a missed
    run once, within its grace").

    A one-off waited ``slot - created_at``; it may run up to half that late,
    no less than 15 minutes and no more than 2 hours — a follow-up is worth
    something only while it is timely. A repeating slot may run until the end
    of its own local day; after that the next slot is the one that counts.
    """
    if isinstance(config.schedule, OnceSchedule):
        half = (slot - created_at) / 2
        return max(timedelta(minutes=15), min(timedelta(hours=2), half))
    local = slot.astimezone()
    end_of_day = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return end_of_day - local
