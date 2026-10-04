"""Why each command is on the command line at all.

The web UI is where Coffer is managed; a command exists only when the web UI
cannot do the job (spec resource-framework "Keep the command line to what
needs it"). Every leaf command carries one of four reasons and a one-line why;
a test walks the live command tree and fails when a command has no row here, or
a row names a command that is gone.
"""

from __future__ import annotations

from enum import Enum


class Reason(Enum):
    #: A program runs it: an installed hook, an agent's key helper.
    PROGRAM = "program"
    #: It must work while the daemon is down.
    OFFLINE = "offline"
    #: A hand-off prompt names it for an agent to run.
    HANDOFF = "handoff"
    #: Nothing in the web UI does this job.
    NO_UI = "no-ui"


#: Space-separated command path -> (reason, why).
COMMAND_REASONS: dict[str, tuple[Reason, str]] = {
    "memory hook": (Reason.PROGRAM, "the installed memory hook runs it"),
    "proxy token": (Reason.PROGRAM, "an agent's key helper runs it"),
    "daemon start": (
        Reason.OFFLINE,
        "the daemon may be down; the desktop shell and the upgrade hand-off name it",
    ),
    "daemon stop": (Reason.OFFLINE, "the desktop shell and the upgrade hand-off name it"),
    "daemon restart": (Reason.OFFLINE, "a changed port applies only after a restart"),
    "daemon status": (Reason.OFFLINE, "the offline banner points at it when the daemon is down"),
    "migrate": (Reason.OFFLINE, "runs with the daemon stopped"),
    "path logs": (
        Reason.OFFLINE,
        "the log files are what is left to read when the daemon will not start",
    ),
    "config list": (Reason.OFFLINE, "only the keys read before the daemon binds (its port)"),
    "config get": (Reason.OFFLINE, "only the keys read before the daemon binds (its port)"),
    "config set": (Reason.OFFLINE, "the port must be changeable when the daemon cannot start"),
    "config unset": (Reason.OFFLINE, "the port must be changeable when the daemon cannot start"),
    "run": (Reason.HANDOFF, "an agent runs a command with secrets set only in its environment"),
    "secret list": (Reason.HANDOFF, "an agent names a secret for `run`"),
    "secret set": (
        Reason.HANDOFF,
        "an agent stores a secret read from stdin without the value entering a chat",
    ),
    "log audit": (Reason.HANDOFF, "troubleshooting hand-offs read records that are not files"),
    "log mcp": (Reason.HANDOFF, "troubleshooting hand-offs read records that are not files"),
    "log daemon": (Reason.HANDOFF, "troubleshooting hand-offs read records that are not files"),
    "mcp test": (Reason.HANDOFF, "the MCP install hand-off verifies the server answers"),
    "vault problems": (
        Reason.NO_UI,
        "lists hand edits the vault refused; no page shows them, and editing files "
        "directly is now the main way to change knowledge",
    ),
}
