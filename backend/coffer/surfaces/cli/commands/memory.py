"""``coffer memory`` — the Memory page, the tidy an agent runs, and the
session-start hook (spec memory "Show and edit memory on the Memory page",
"Tidy memory as one change", "Hand a session its project's memories at start").

Memory is plain files under ``~/.coffer/vault/memory/projects/``: agents and
people read and write them with their own tools. The commands here list them,
open and close a tidy, and print what a session is handed.
"""

from __future__ import annotations

import json
import os
import sys

import typer

from coffer.surfaces.cli._route_command import RouteCommand, mount
from coffer.surfaces.cli.groups import group

_UI = "Memory · "

SPECS = [
    RouteCommand(
        "memory state",
        "GET",
        "/memory",
        _UI + "the page",
        "The projects that hold memories, whether a tidy is open, and the Tidy prompt.",
        rows="projects",
        columns=("folder", "topics", "problems", "updated"),
    ),
    RouteCommand(
        "memory topics",
        "GET",
        "/memory/projects/{project}",
        _UI + "a project's memories",
        "A project's memory files, with what breaks the format in each.",
        args={"project": "The project's folder (from coffer memory state)"},
        rows="topics",
        columns=("name", "title", "type", "updated"),
    ),
    RouteCommand(
        "memory show",
        "GET",
        "/memory/projects/{project}/{name}",
        _UI + "a memory file",
        "One memory file's text.",
        args={
            "project": "The project's folder",
            "name": "The file's name (from coffer memory topics)",
        },
    ),
    RouteCommand(
        "memory tidy-start",
        "POST",
        "/memory/tidy/start",
        _UI + "Tidy (an agent starts it)",
        "Open a tidy: until it finishes, the edits under memory/ are kept for one commit.",
    ),
    RouteCommand(
        "memory tidy-finish",
        "POST",
        "/memory/tidy/finish",
        _UI + "Tidy (an agent finishes it)",
        "Close the tidy and commit its edits as one commit. Body: summary (the agent's report).",
        body=True,
    ),
]

mount(SPECS)


@group("memory").command("session-start")
def session_start() -> None:
    """Print the memories a session started here is handed (the agents' hook runs it).

    Reads the hook's JSON from standard input for the session's working
    directory, falling back to the current directory. Prints nothing outside
    a repository, and nothing in a session Coffer started itself, whose
    system prompt already carries them. Never fails a session: any error
    prints nothing and exits 0. Needs no running daemon.
    """
    try:
        from coffer.application.memory.context import INJECTED_ENV, session_context
        from coffer.infrastructure.vault.home import vault_root

        if os.environ.get(INJECTED_ENV):
            return
        cwd = os.getcwd()
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            try:
                payload = json.loads(raw) if raw.strip() else {}
            except ValueError:
                payload = {}
            if isinstance(payload, dict) and isinstance(payload.get("cwd"), str):
                cwd = payload["cwd"]
        text = session_context(cwd, vault=vault_root())
        if text:
            typer.echo(text, nl=False)
    except Exception:
        return
