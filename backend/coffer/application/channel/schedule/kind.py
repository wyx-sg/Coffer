"""The ``scheduled_task`` Kind, wired by the composition root (spec channels
"Keep scheduled tasks as machine-local resources").

A scheduled task is a resource like every other user-managed thing: one file
with an immutable uid, a free-text name, an enabled switch (paused or active)
and the audit trail every kind gets. It is filed under ``local/``: the agent
and directory it names are this machine's, and a task that travelled would run
on every machine at once.

Both write paths — the task routes and the kind-agnostic resource routes —
check here that the schedule can run as written, so an edit cannot sneak in
what a create would refuse.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from coffer.domain.channel.schedule import MIN_REPEAT, OnceSchedule, shortest_gap
from coffer.domain.channel.scheduled_task import (
    OLD_CONFIG_KEYS,
    ScheduledTaskConfig,
    min_repeat_ok,
)
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, Resource
from coffer.domain.vault.layout import StorageClass

__all__ = ["KIND", "check_schedule", "make_scheduled_task_kind"]

KIND = "scheduled_task"


def check_schedule(config: ScheduledTaskConfig, *, now: datetime, new: bool) -> None:
    """Refuse a schedule that cannot run as written: a one-off already behind
    (when it is being set), or a repeating one tighter than :data:`MIN_REPEAT`."""
    schedule = config.schedule
    if new and isinstance(schedule, OnceSchedule) and schedule.at <= now:
        raise ValueError(f"{schedule.at.isoformat()} is already in the past")
    if not min_repeat_ok(schedule, shortest_gap(schedule, start=now)):
        minutes = int(MIN_REPEAT.total_seconds() // 60)
        raise ValueError(f"a repeating task runs at most once every {minutes} minutes")


def make_scheduled_task_kind(
    *,
    prompt_of: Callable[[str], str | None] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> Kind:
    """Construct the ``scheduled_task`` Kind."""

    async def _validate_create(config: dict[str, Any]) -> None:
        check_schedule(ScheduledTaskConfig.model_validate(config), now=clock(), new=True)

    def _has_prompt(resource: Resource) -> None:
        # A task is created paused until its PROMPT.md is written, and stays so.
        if prompt_of is not None and not (prompt_of(resource.uid) or "").strip():
            raise ConfigValidationError("write the task's PROMPT.md before resuming it")

    async def _validate_update(resource: Resource, after: dict[str, Any]) -> None:
        # A file from before 2026-11-11 still carries its prompt or directory
        # while they are being taken out of it.
        old = {k: v for k, v in resource.config.items() if k not in OLD_CONFIG_KEYS}
        before = ScheduledTaskConfig.model_validate(old).schedule
        parsed = ScheduledTaskConfig.model_validate(after)
        try:
            # A one-off whose time is not being changed may already be behind.
            check_schedule(parsed, now=clock(), new=parsed.schedule != before)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e

    return Kind(
        name=KIND,
        display_name="Scheduled task",
        config_schema=ScheduledTaskConfig,
        free_name=True,
        storage=StorageClass.LOCAL,
        validate_config=_validate_create,
        on_update_config=_validate_update,
        before_enable=_has_prompt if prompt_of is not None else None,
    )
