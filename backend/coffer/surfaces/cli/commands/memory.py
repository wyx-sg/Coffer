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
        "memory show",
        "GET",
        "/memory/sync/entries/{entry_id}",
        _UI + "a memory",
        "One memory's text and the file each agent on this machine holds it in.",
        args={"entry_id": "The memory's id (from coffer memory entries)"},
    ),
    RouteCommand(
        "memory curate",
        "POST",
        "/memory/sync/curation/handoff",
        _UI + "Curate now",
        "The prompt that asks Claude Code to consolidate its memory; give it to the agent. "
        "Body: agent_type.",
        body=True,
    ),
    RouteCommand(
        "memory curation-enable",
        "POST",
        "/memory/sync/curation/enable",
        _UI + "agent · Memory · Turn on (Auto Dream)",
        "Turn on an agent's own curation in its settings, backed up first. Body: agent_type.",
        body=True,
    ),
]

mount(SPECS)
