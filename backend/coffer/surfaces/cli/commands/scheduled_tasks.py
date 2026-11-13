"""``coffer task`` — the Scheduled tasks page.

Spec scheduled-tasks "Manage scheduled tasks from the Scheduled tasks page". Editing,
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
        "One task: its config, prompt, folder, next run and last run.",
        names=T,
    ),
    RouteCommand(
        "task add",
        "POST",
        "/scheduled-tasks",
        _UI + "New task",
        "Add a scheduled task. Body: prompt (written to the task's PROMPT.md, which "
        "`task prompt` replaces later), name (optional: the prompt's first words "
        "otherwise), description, config (schedule with an optional IANA timezone, agent, "
        "model, cwd). Every run opens a new conversation on the agent in cwd, an "
        "absolute path, or in the task's own folder when it names none.",
        body=True,
    ),
    RouteCommand(
        "task prompt",
        "PUT",
        "/scheduled-tasks/{uid}/prompt",
        _UI + "Prompt · Edit",
        "Replace a task's PROMPT.md (or edit that file in its folder). Body: prompt.",
        names=T,
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
