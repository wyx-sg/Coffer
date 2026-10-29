"""The message a scheduled run hands the agent (spec channels "Open every
scheduled run with what the task is").

A run is a turn like any other, so it opens with a block that says where it
came from, the way a message's turn opens with its origin. The block names the
task, when it was due and when it is really running (a run that is late — the
Mac slept, Coffer was stopped — says so, so the agent can judge whether the
work still makes sense), whom to address, the task's own words, and the two
rules every run shares: a reply opening with ``[SILENT]`` is not sent, and a
follow-up that is not settled may book the next one.

Every line the task's author wrote is untrusted text inside the block and is
neutralised, exactly as a person's message is.
"""

from __future__ import annotations

from datetime import datetime

from coffer.domain.channel.schedule import OnceSchedule, Schedule
from coffer.domain.channel.scheduled_task import (
    CHAIN_MAX_RUNS,
    CHAIN_MAX_SPAN,
    SILENT_MARK,
    ScheduledTaskConfig,
)
from coffer.domain.turn_markers import (
    MATERIAL,
    MATERIAL_END,
    SCHEDULED,
    SCHEDULED_END,
    block,
    neutralise,
)

__all__ = ["describe_schedule", "local_time", "run_message"]


def local_time(moment: datetime) -> str:
    """``2026-10-29 15:30 (UTC+08:00)``: this machine's wall clock, with its offset."""
    local = moment.astimezone()
    offset = local.strftime("%z")
    return f"{local:%Y-%m-%d %H:%M} (UTC{offset[:3]}:{offset[3:]})"


_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def describe_schedule(schedule: Schedule) -> str:
    """The schedule in a few English words, for the agent (the UI words its own)."""
    kind = schedule.kind
    if isinstance(schedule, OnceSchedule):
        return f"once, at {local_time(schedule.at)}"
    if kind == "hourly":
        return f"every hour at :{schedule.minute:02d}"  # type: ignore[union-attr]
    if kind == "daily":
        return f"every day at {schedule.time}"  # type: ignore[union-attr]
    if kind == "weekdays":
        return f"Monday to Friday at {schedule.time}"  # type: ignore[union-attr]
    if kind == "weekly":
        day = _WEEKDAYS[schedule.weekday]  # type: ignore[union-attr]
        return f"every {day} at {schedule.time}"  # type: ignore[union-attr]
    if kind == "cron":
        return f"cron `{schedule.expr}` (local time)"  # type: ignore[union-attr]
    return "only when someone runs it"


def _what_it_is(config: ScheduledTaskConfig, created_at: datetime) -> list[str]:
    if config.origin == "agent":
        started = config.chain_started_at or created_at
        lines = [
            f"kind: a follow-up you booked for yourself at {local_time(created_at)}",
            f"follow-up: {config.chain_index} of at most {CHAIN_MAX_RUNS}, "
            f"the chain ends {local_time(started + CHAIN_MAX_SPAN)}",
        ]
        if config.chain_index >= CHAIN_MAX_RUNS:
            lines.append(
                "this is the last follow-up of the chain: give a conclusion now, "
                "even if it is that the matter is still open"
            )
        return lines
    return [f"kind: a task the owner set up, {describe_schedule(config.schedule)}"]


def run_message(
    *,
    name: str,
    uid: str,
    config: ScheduledTaskConfig,
    created_at: datetime,
    due_at: datetime,
    now: datetime,
    late: bool,
    manual: bool,
    material: str = "",
) -> str:
    """The whole text of the run's turn: the task block, then any material."""
    chat = config.chat
    lines = [
        f"task: {neutralise(name)} (id: {uid})",
        *_what_it_is(config, created_at),
        f"channel id: {chat.channel} · chat_id: {chat.chat_id} · chat_kind: {chat.chat_kind}"
        + (f" · thread_id: {chat.thread_id}" if chat.thread_id else ""),
    ]
    if manual:
        lines.append(f"started by hand at {local_time(now)}")
    elif late:
        lines.append(
            f"due: {local_time(due_at)}, running now at {local_time(now)} — late, because "
            "this computer was asleep or Coffer was not running; judge whether the work "
            "still makes sense before doing it"
        )
    else:
        lines.append(f"due: {local_time(due_at)}")
    if config.mention is not None and config.mention.name:
        lines.append(f"asked by: {neutralise(config.mention.name)} (your reply mentions them)")
    lines.append("")
    lines.append("What to do:")
    lines.extend(neutralise(config.prompt).splitlines())
    lines.append("")
    lines.append(
        f"If there is nothing worth telling, reply with {SILENT_MARK} as the very first "
        "word and nothing is sent to the chat."
    )
    if config.origin == "agent":
        lines.append(
            "If it is not settled yet, book the next follow-up with "
            "coffer__schedule_task and say so in one line, or reply "
            f"{SILENT_MARK}."
        )
    text = block(SCHEDULED, SCHEDULED_END, lines)
    if material:
        text += "\n\n" + block(MATERIAL, MATERIAL_END, material.splitlines())
    return text
