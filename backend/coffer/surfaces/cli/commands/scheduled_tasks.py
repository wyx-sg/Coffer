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
        columns=("name", "enabled", "next_run", "uid"),
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
        "Add a scheduled task. Body: name, description, config (schedule with an "
        "optional IANA timezone, prompt, agent, model, cwd). Every run opens a new "
        "conversation on the agent.",
        body=True,
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
]

mount(SPECS)
