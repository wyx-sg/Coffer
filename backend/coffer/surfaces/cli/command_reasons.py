"""Why a command that stands for no UI operation is on the command line.

Every web UI and desktop operation has a command, recorded with its route in
``registry`` (spec resource-framework "Offer every management operation on the
command line"). The commands below are the rest: no page offers them, and each
carries one of four reasons and a one-line why. A test walks the live command
tree and fails when a leaf is neither in the registry nor here, or when a row
here names a command that is gone or one the registry already records.
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
    "proxy token": (Reason.PROGRAM, "an agent's key helper runs it"),
    "daemon start": (
        Reason.OFFLINE,
        "the daemon may be down; the desktop shell and the upgrade hand-off name it",
    ),
    "daemon stop": (Reason.OFFLINE, "the desktop shell and the upgrade hand-off name it"),
    "daemon restart": (Reason.OFFLINE, "a changed port applies only after a restart"),
    "path logs": (
        Reason.OFFLINE,
        "the log files are what is left to read when the daemon will not start",
    ),
    "path skill-data": (
        Reason.PROGRAM,
        "a skill's scripts run it to find where their logs, journals and temp files go",
    ),
    "config list": (Reason.OFFLINE, "only the keys read before the daemon binds (its port)"),
    "config get": (Reason.OFFLINE, "only the keys read before the daemon binds (its port)"),
    "config set": (Reason.OFFLINE, "the port must be changeable when the daemon cannot start"),
    "config unset": (Reason.OFFLINE, "the port must be changeable when the daemon cannot start"),
    "run": (Reason.HANDOFF, "an agent runs a command with secrets set only in its environment"),
}
