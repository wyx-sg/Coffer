"""The ``scheduled_task`` Kind, wired by the composition root (spec channels
"Keep scheduled tasks as machine-local resources").

A scheduled task is a resource like every other user-managed thing: one file
with an immutable uid, a free-text name, an enabled switch (paused or active)
and the audit trail every kind gets. It belongs to the channel package because
everything it does happens in a channel's chat (ADR
scheduled-tasks-are-turns-coffer-starts-in-a-chat), and it is filed under
``local/`` like a channel: the chat, agent and directory it names are this
machine's, and a task that travelled would run on every machine at once.

Both write paths — the task routes, the agent's tools and the kind-agnostic
resource routes — check here that the chat is one the channel has paired and
that the schedule can run as written, so an edit cannot sneak in what a create
would refuse. The follow-up limits are the agent's tools' own
(:class:`~coffer.application.channel.schedule.tasks.TaskService`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from coffer.domain.channel.schedule import MIN_REPEAT, OnceSchedule, shortest_gap
from coffer.domain.channel.scheduled_task import ScheduledTaskConfig, min_repeat_ok
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, Resource
from coffer.domain.vault.layout import StorageClass

__all__ = ["KIND", "check_schedule", "make_scheduled_task_kind"]

KIND = "scheduled_task"

#: Every channel this vault holds, by uid: what a task's chat must name.
ChannelUids = Callable[[], Awaitable[set[str]]]
#: Whether a channel (uid) has paired a chat (id).
ChatPaired = Callable[[str, str], Awaitable[bool]]


def check_schedule(config: ScheduledTaskConfig, *, now: datetime, new: bool) -> None:
    """Refuse a schedule that cannot run as written: a one-off already behind
    (when it is being set), or a repeating one tighter than :data:`MIN_REPEAT`."""
    schedule = config.schedule
    if new and isinstance(schedule, OnceSchedule) and schedule.at <= now:
        raise ValueError(f"{schedule.at.isoformat()} is already in the past")
    if not min_repeat_ok(schedule, shortest_gap(schedule, start=now)):
        minutes = int(MIN_REPEAT.total_seconds() // 60)
        raise ValueError(f"a repeating task runs at most once every {minutes} minutes")


async def _check(
    config: dict[str, Any],
    channels: ChannelUids | None,
    paired: ChatPaired | None,
    *,
    new: bool,
    clock: Callable[[], datetime],
) -> None:
    parsed = ScheduledTaskConfig.model_validate(config)
    check_schedule(parsed, now=clock(), new=new)
    chat = parsed.chat
    if channels is not None and chat.channel not in await channels():
        raise ValueError(f"no channel {chat.channel!r} on this machine")
    if paired is not None and not await paired(chat.channel, chat.chat_id):
        raise ValueError(
            f"chat {chat.chat_id!r} is not paired with this channel; "
            "a task runs only in a chat the owner uses with the bot"
        )


def make_scheduled_task_kind(
    *,
    channels: ChannelUids | None = None,
    paired: ChatPaired | None = None,
    on_delete: Callable[[Resource], Awaitable[None]] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> Kind:
    """Construct the ``scheduled_task`` Kind. ``channels`` and ``paired``
    (injected by the composition root) say which channels and chats a task may
    name; without them (a bare test app) only the schedule is checked."""

    async def _validate_create(config: dict[str, Any]) -> None:
        await _check(config, channels, paired, new=True, clock=clock)

    async def _validate_update(resource: Resource, after: dict[str, Any]) -> None:
        before = ScheduledTaskConfig.model_validate(resource.config).schedule
        try:
            await _check(
                after,
                channels,
                paired,
                # A one-off whose time is not being changed may already be behind.
                new=ScheduledTaskConfig.model_validate(after).schedule != before,
                clock=clock,
            )
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
        on_delete=on_delete,
    )
