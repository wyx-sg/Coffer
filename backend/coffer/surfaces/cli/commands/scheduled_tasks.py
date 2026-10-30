"""``coffer task`` — the Scheduled tasks page.

Spec channels "Manage scheduled tasks from the Scheduled tasks page". Editing,
pausing (``disable``), resuming (``enable``) and deleting a task are its
resource verbs (``coffer task update`` …, declared with the other kinds'); these
are a task's own reads, with next and last runs, and its own actions.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import Q, RouteCommand, mount

T = {"uid": "scheduled_task"}
_UI = "Scheduled tasks · "

SPECS = [
    RouteCommand(
        "task list",
        "GET",
        "/scheduled-tasks",
        _UI + "list",
        "Every scheduled task, with its next and last run.",
        rows="items",
        columns=("name", "enabled", "next_run", "channel_name", "uid"),
    ),
    RouteCommand(
        "task show",
        "GET",
        "/scheduled-tasks/{uid}",
        _UI + "open a task",
        "One task: its config, next run and last run.",
        names=T,
    ),
    RouteCommand(
        "task add",
        "POST",
        "/scheduled-tasks",
        _UI + "New task",
        "Add a scheduled task. Body: name, description, config (schedule, prompt, chat "
        "{channel, chat_id}, session continue|fresh, agent, cwd, model).",
        body=True,
    ),
    RouteCommand(
        "task chats",
        "GET",
        "/scheduled-tasks/chats",
        _UI + "New task · where it runs",
        "The paired chats a task may run in.",
        rows="items",
        columns=("channel_name", "chat_kind", "label", "chat_id", "channel"),
    ),
    RouteCommand(
        "task run",
        "POST",
        "/scheduled-tasks/{uid}/run",
        _UI + "Run now",
        "Run a task once, now, whatever its schedule.",
        names=T,
    ),
    RouteCommand(
        "task runs",
        "GET",
        "/scheduled-tasks/{uid}/runs",
        _UI + "a task's run history",
        "A task's runs, newest first: when, and how each ended.",
        names=T,
        query=(Q("limit", kind=int),),
        rows="items",
        columns=("started_at", "trigger", "outcome", "reason"),
    ),
    RouteCommand(
        "task daily-report",
        "PUT",
        "/scheduled-tasks/daily-report",
        "Channels · Daily report",
        "Set the daily report's time, made from its template the first time. Body: "
        "channel, time (HH:MM), agent.",
        body=True,
    ),
]

mount(SPECS)
