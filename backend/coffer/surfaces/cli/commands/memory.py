"""``coffer memory`` — the Memory page.

Spec memory "Manage memory sync in the web UI and on the command line". The hub and each agent's own
memory are plain files, read and edited with the reader's own tools; the sync,
its preview, undo, the Codex import switch and curation are commands.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import Q, RouteCommand, mount

_UI = "Memory · "

SPECS = [
    RouteCommand(
        "memory state",
        "GET",
        "/memory/sync/state",
        _UI + "the page",
        "The sync, its pending preview, the hub's projects and each agent's state.",
    ),
    RouteCommand(
        "memory sync",
        "POST",
        "/memory/sync/run",
        _UI + "Sync now",
        "Sync memory now.",
    ),
    RouteCommand(
        "memory preview-write",
        "POST",
        "/memory/sync/preview/write",
        _UI + "preview · Write",
        "Write exactly what the pending preview lists.",
    ),
    RouteCommand(
        "memory preview-cancel",
        "POST",
        "/memory/sync/preview/cancel",
        _UI + "preview · Cancel",
        "Drop the pending preview.",
    ),
    RouteCommand(
        "memory undo",
        "POST",
        "/memory/sync/undo",
        _UI + "Undo sync…",
        "Remove every unedited copy Coffer wrote on this machine and turn automatic sync off.",
    ),
    RouteCommand(
        "memory codex-import",
        "PUT",
        "/memory/sync/codex-import",
        _UI + "Codex imports Claude Code's memories itself",
        "Say whether Codex imports Claude Code's memories itself. Body: value (true, false, null).",
        body=True,
    ),
    RouteCommand(
        "memory entries",
        "GET",
        "/memory/sync/entries",
        _UI + "a project's memories",
        "A project's memories with their origin and where each was written.",
        query=(Q("project", "The project key, or global"),),
        rows="entries",
        columns=("title", "origin_agent", "origin_machine", "type"),
    ),
    RouteCommand(
        "memory curate",
        "POST",
        "/memory/sync/curate",
        _UI + "Curate now",
        "Ask an agent to consolidate its own memory now. Body: agent_type.",
        body=True,
    ),
]

mount(SPECS)
