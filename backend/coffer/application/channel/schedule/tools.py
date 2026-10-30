"""The built-in tools an agent schedules with from inside a channel turn (spec
channels "Let an agent book a follow-up in the thread it is answering").

``coffer__schedule_task`` books a follow-up in the thread the turn is
answering — "I'll check again once the deploy is done" — or, when the owner
asked for one there, any task: every weekday at nine, in a fresh conversation.
``coffer__scheduled_tasks`` lists what waits in this thread, and
``coffer__cancel_scheduled_task`` cancels one of them.

All three are turn-scoped: offered only inside a turn Coffer runs, and told by
the gateway which turn is calling (``TURN_ARGUMENT``), so the chat, the thread
and the asker come from the turn itself and never from what the agent copied
out of its prompt. A turn someone who may only ask started schedules nothing,
and neither does a run of a repeating task. While the ``scheduled_tasks``
experimental feature is off the three are withdrawn from every turn.

Application layer only; the composition root registers them.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import TypeAdapter, ValidationError

from coffer.application.builtin_tools import BuiltinTool
from coffer.application.channel import turn_origin
from coffer.application.channel.schedule.message import describe_schedule, local_time
from coffer.application.channel.schedule.tasks import TaskService
from coffer.application.resource_service import ResourceService
from coffer.application.turn_scope import TURN_ARGUMENT
from coffer.domain.channel.schedule import Schedule
from coffer.domain.errors import CofferError
from coffer.domain.features import SCHEDULED_TASKS

__all__ = ["ScheduleTools", "parse_after", "parse_at", "schedule_tools"]

_SCHEDULE: TypeAdapter[Schedule] = TypeAdapter(Schedule)
_AFTER = re.compile(r"(\d+)\s*([dhm])", re.IGNORECASE)

#: Turns a turn token into the conversation it is running in (the chat kind's
#: ``turn_tokens.conversation_of``, injected).
ConversationOf = Callable[[str | None], str | None]


def parse_after(raw: str) -> timedelta:
    """``30m``, ``2h``, ``1d``, ``1h30m`` → a duration."""
    text = raw.replace(" ", "")
    if not text or _AFTER.sub("", text):
        raise ValueError("`after` is a duration such as 30m, 2h, 1d or 1h30m")
    units = {"d": "days", "h": "hours", "m": "minutes"}
    total = timedelta()
    for amount, unit in _AFTER.findall(text):
        total += timedelta(**{units[unit.lower()]: int(amount)})
    return total


def parse_at(raw: str) -> datetime:
    """An ISO time; one without an offset is this machine's local time."""
    try:
        value = datetime.fromisoformat(raw.strip())
    except ValueError as e:
        raise ValueError("`at` is an ISO time such as 2026-10-30T09:00") from e
    return value if value.tzinfo is not None else value.astimezone()


def _text(args: dict[str, Any], key: str, *, required: bool = False) -> str | None:
    value = args.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"`{key}` is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"`{key}` must be a string")
    return value.strip()


_SCHEDULE_DESCRIPTION = (
    "Schedule a turn in this chat thread. Use it to follow up on something that "
    "is not settled yet (a deploy, a fix, someone's answer): pass `after` (e.g. 30m, "
    "2h) or `at` (ISO local time) and `prompt`, written for yourself later, e.g. "
    '"Check that X reached live and login works again". When that time comes, '
    "Coffer starts a turn here with the prompt; you answer in the thread (the asker "
    "is mentioned), book another follow-up if it is still not settled, or reply "
    "[SILENT] to say nothing. Follow-ups are 5 minutes to 7 days away, at most 3 "
    "wait per thread. Only when the owner asks for a recurring or separate task, "
    'pass `repeat` (a schedule: {kind: daily|weekdays, time: "HH:MM"}, {kind: '
    "weekly, weekday: 0-6, time}, {kind: hourly, minute}, {kind: cron, expr}) "
    "and/or `fresh: true` (run in a new conversation each time)."
)

_SCHEDULE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "What to do when it runs."},
        "after": {"type": "string", "description": "How long from now: 30m, 2h, 1d, 1h30m."},
        "at": {"type": "string", "description": "When, as an ISO time (local if no offset)."},
        "name": {"type": "string", "description": "A short name for the list (optional)."},
        "repeat": {
            "type": "object",
            "description": "A repeating schedule, only when the owner asked for one.",
        },
        "fresh": {
            "type": "boolean",
            "description": "Run in a new conversation each time (owner's tasks only).",
        },
    },
    "required": ["prompt"],
}

_TURN_ONLY: dict[str, Any] = {"type": "object", "properties": {}}

_CANCEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "string", "description": "The task's id."}},
    "required": ["id"],
}


class ScheduleTools:
    def __init__(
        self,
        *,
        tasks: TaskService,
        resources: ResourceService,
        conversation_of: ConversationOf,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._tasks = tasks
        self._resources = resources
        self._conversation_of = conversation_of
        self._clock = clock

    def _origin(self, args: dict[str, Any]) -> turn_origin.TurnOrigin:
        conversation_id = self._conversation_of(args.get(TURN_ARGUMENT))
        origin = turn_origin.origin_of(conversation_id) if conversation_id else None
        if origin is None:
            raise ValueError("this tool works only inside a channel turn Coffer is running")
        return origin

    async def schedule(self, args: dict[str, Any]) -> dict[str, Any]:
        origin = self._origin(args)
        prompt = _text(args, "prompt", required=True) or ""
        at_raw, after_raw = _text(args, "at"), _text(args, "after")
        repeat_raw = args.get("repeat")
        if at_raw and after_raw:
            raise ValueError("pass `at` or `after`, not both")
        now = self._clock()
        at = parse_at(at_raw) if at_raw else now + parse_after(after_raw) if after_raw else None
        repeat = None
        if repeat_raw is not None:
            try:
                repeat = _SCHEDULE.validate_python(repeat_raw).model_dump(mode="json")
            except ValidationError as e:
                raise ValueError(f"`repeat` is not a schedule: {e.errors()[0]['msg']}") from e
        if at is None and repeat is None:
            raise ValueError("say when: `after`, `at` or `repeat`")
        try:
            task = await self._tasks.book(
                origin,
                prompt=prompt,
                at=at or now,
                repeat=repeat,
                fresh=bool(args.get("fresh")),
                name=_text(args, "name"),
                actor=str(args.get("agent") or "agent"),
            )
        except CofferError as e:
            raise ValueError(str(e)) from e
        view = await self._tasks.view(task.uid)
        return {
            "id": task.uid,
            "name": task.name,
            "runs": describe_schedule(view.config.schedule),
            "next_run": local_time(view.next_run) if view.next_run else None,
        }

    async def list_here(self, args: dict[str, Any]) -> dict[str, Any]:
        origin = self._origin(args)
        views = await self._tasks.waiting_in(
            origin.channel_uid, origin.chat_id, origin.conversation_thread_id
        )
        return {
            "tasks": [
                {
                    "id": v.task.uid,
                    "name": v.task.name,
                    "prompt": v.config.prompt,
                    "booked_by": v.config.origin,
                    "runs": describe_schedule(v.config.schedule),
                    "next_run": local_time(v.next_run) if v.next_run else None,
                }
                for v in views
            ]
        }

    async def cancel(self, args: dict[str, Any]) -> dict[str, Any]:
        origin = self._origin(args)
        if not origin.asker_is_owner:
            raise ValueError("only the bot's owners can cancel a scheduled task")
        uid = _text(args, "id", required=True) or ""
        here = await self._tasks.waiting_in(
            origin.channel_uid, origin.chat_id, origin.conversation_thread_id
        )
        match = next((v for v in here if v.task.uid == uid), None)
        if match is None:
            raise ValueError(f"no task {uid!r} waits in this thread")
        await self._resources.delete(uid, str(args.get("agent") or "agent"))
        return {"cancelled": uid, "name": match.task.name}


def schedule_tools(tools: ScheduleTools) -> list[BuiltinTool]:
    """The registry entries, all turn-scoped."""
    return [
        BuiltinTool(
            name="schedule_task",
            description=_SCHEDULE_DESCRIPTION,
            input_schema=_SCHEDULE_SCHEMA,
            handler=tools.schedule,
            turn_scoped=True,
            feature=SCHEDULED_TASKS,
        ),
        BuiltinTool(
            name="scheduled_tasks",
            description="List the scheduled tasks and follow-ups waiting in this chat thread.",
            input_schema=_TURN_ONLY,
            handler=tools.list_here,
            turn_scoped=True,
            feature=SCHEDULED_TASKS,
        ),
        BuiltinTool(
            name="cancel_scheduled_task",
            description="Cancel a scheduled task or follow-up waiting in this chat thread.",
            input_schema=_CANCEL_SCHEMA,
            handler=tools.cancel,
            turn_scoped=True,
            feature=SCHEDULED_TASKS,
        ),
    ]
