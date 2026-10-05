"""``coffer memory`` — the Memory page (``memory hook`` predates this module).

Spec memory "Manage memory in the web UI and on the command line". Memory notes
are plain Markdown files under the memory root, read and edited with the
reader's own tools; the partitions, what each delivers, a sync pass and the
tidy hand-off are commands.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import RouteCommand, mount

P = {"uid": "memory"}
_UI = "Memory · "

SPECS = [
    RouteCommand(
        "memory partitions",
        "GET",
        "/memory/partitions",
        _UI + "partitions",
        "Every memory partition.",
    ),
    RouteCommand(
        "memory notes",
        "GET",
        "/memory/partitions/{uid}/notes",
        _UI + "a partition's notes",
        "A partition's notes and their paths (read them with your own tools).",
        names=P,
    ),
    RouteCommand(
        "memory files",
        "GET",
        "/memory/partitions/{uid}/files",
        _UI + "a partition's files",
        "A partition's files.",
        names=P,
    ),
    RouteCommand(
        "memory delivered",
        "GET",
        "/memory/partitions/{uid}/delivered",
        _UI + "what agents are given",
        "What the partition delivers to agents.",
        names=P,
    ),
    RouteCommand(
        "memory retired",
        "GET",
        "/memory/partitions/{uid}/retired",
        _UI + "retired notes",
        "Notes retired from delivery.",
        names=P,
    ),
    RouteCommand(
        "memory reading",
        "GET",
        "/memory/reading",
        _UI + "what Coffer reads",
        "Which agents' memory Coffer reads, and where.",
    ),
    RouteCommand(
        "memory sync",
        "POST",
        "/memory/sync",
        _UI + "Sync now",
        "Read the agents' memory again now.",
    ),
    RouteCommand(
        "memory tidy-handoff",
        "GET",
        "/memory/tidy-handoff",
        _UI + "Tidy with an agent",
        "The prompt that hands tidying memory to an agent.",
    ),
]

mount(SPECS)
