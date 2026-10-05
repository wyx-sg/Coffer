"""``coffer daemon`` beyond its offline verbs — Settings > Daemon.

Spec daemon. ``daemon start/stop/restart/status`` work while the daemon is down;
these ask the running daemon.
"""

from __future__ import annotations

from coffer.surfaces.cli._route_command import RouteCommand, mount

_UI = "Settings · Daemon · "

SPECS = [
    RouteCommand(
        "daemon port show",
        "GET",
        "/daemon/port",
        _UI + "port",
        "The port the daemon serves and the one its next start uses.",
    ),
    RouteCommand(
        "daemon port set",
        "PUT",
        "/daemon/port",
        _UI + "port",
        "Set the port of the next start. Body: port.",
        body=True,
    ),
    RouteCommand(
        "daemon residency show",
        "GET",
        "/daemon/residency",
        _UI + "start at login",
        "Whether the daemon starts at login.",
    ),
    RouteCommand(
        "daemon residency set",
        "PUT",
        "/daemon/residency",
        _UI + "start at login",
        "Install or remove the login service. Body: login_service_installed.",
        body=True,
    ),
    RouteCommand(
        "daemon reload",
        "POST",
        "/daemon/restart",
        _UI + "Restart daemon",
        "Ask the running daemon to restart itself.",
    ),
    RouteCommand(
        "daemon rotate-token",
        "POST",
        "/daemon/rotate-token",
        _UI + "Rotate token",
        "Mint a new daemon token (clients re-read daemon.json).",
    ),
    RouteCommand(
        "daemon upgrade",
        "GET",
        "/daemon/upgrade",
        _UI + "upgrade",
        "Whether this daemon is older than the installed Coffer, and the hand-off.",
    ),
    RouteCommand(
        "daemon setup-check",
        "POST",
        "/daemon/setup/check",
        "Setup · Check again",
        "Look for git again while the daemon waits in its setup state.",
    ),
    RouteCommand(
        "daemon upkeep",
        "GET",
        "/upkeep/runs",
        _UI + "passes in flight",
        "The rewriting passes running now.",
    ),
]

mount(SPECS)
