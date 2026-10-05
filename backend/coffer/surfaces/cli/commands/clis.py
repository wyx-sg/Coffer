"""``coffer cli`` — the CLIs page (``cli list`` predates this module).

Spec skill-manager "Declare a command-line tool without a skill" and web-ui
"Show every CLI a skill requires on the CLIs page". A tool is
named by its command (``gh``, ``jq``).
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import RouteCommand, mount

_UI = "CLIs · "

SPECS = [
    RouteCommand(
        "cli show",
        "GET",
        "/clis/{command}",
        _UI + "open a tool",
        "One tool: where it is found, its version, its login state, who needs it.",
    ),
    RouteCommand(
        "cli add",
        "POST",
        "/clis",
        _UI + "Add CLI",
        "Add a tool by hand. Body: command, title, description, min_version, login_check.",
        body=True,
    ),
    RouteCommand(
        "cli preview",
        "POST",
        "/clis/preview",
        _UI + "Add CLI · preview",
        "What Coffer finds for a command before it is added. Body: command.",
        body=True,
    ),
    RouteCommand(
        "cli update",
        "PATCH",
        "/clis/{command}",
        _UI + "edit a tool",
        "Change a tool. Body: title, description, min_version, login_check.",
        body=True,
    ),
    RouteCommand(
        "cli remove", "DELETE", "/clis/{command}", _UI + "Remove", "Remove a tool added by hand."
    ),
    RouteCommand(
        "cli check",
        "POST",
        "/clis/{command}/check",
        _UI + "Check again",
        "Look for one tool again.",
    ),
    RouteCommand(
        "cli check-all", "POST", "/clis/check", _UI + "Check all", "Look for every tool again."
    ),
]

mount(SPECS)
