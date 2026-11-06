"""The message a scheduled run hands the agent (spec channels "Run a scheduled
task in a fresh conversation of its own").

The task's prompt, as the owner wrote it — what Claude Code's and Codex's own
automations send. A run that is late (the Mac slept, Coffer was stopped) or
started by hand says so in one line after it, so the agent can judge whether
the work still makes sense.
"""

from __future__ import annotations

from datetime import datetime

__all__ = ["local_time", "run_message"]


def local_time(moment: datetime) -> str:
    """``2026-10-29 15:30 (UTC+08:00)``: this machine's wall clock, with its offset."""
    local = moment.astimezone()
    offset = local.strftime("%z")
    return f"{local:%Y-%m-%d %H:%M} (UTC{offset[:3]}:{offset[3:]})"


def run_message(*, prompt: str, due_at: datetime, now: datetime, late: bool, manual: bool) -> str:
    """The whole text of the run's turn."""
    if manual:
        return prompt
    if late:
        return (
            f"{prompt}\n\n(This scheduled run was due at {local_time(due_at)} and is running "
            f"late, at {local_time(now)}, because this computer was asleep or Coffer was not "
            "running. Judge whether the work still makes sense before doing it.)"
        )
    return prompt
