"""Shared CLI options + exit code conventions.

Exit codes match the convention in .agents/workflow.md / the rest of the
CLI surface: 0 success, 1 generic, 2 invalid usage (Typer's default),
3 daemon unreachable, 4 not found, 5 conflict, 6 invalid input,
7 upstream test failed, 8 secret issue, 9 approval pending, 10 the daemon
waits for git, 11 a presence check was not confirmed, 12 the desktop app is
not available, 13 a ``--wait`` ran out (spec resource-framework "Offer every
management operation on the command line").
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    GENERIC = 1
    INVALID_USAGE = 2
    DAEMON_UNREACHABLE = 3
    NOT_FOUND = 4
    CONFLICT = 5
    INVALID_INPUT = 6
    UPSTREAM_TEST_FAILED = 7
    SECRET_ISSUE = 8
    #: A change is saved but waits for a person to approve it in the Coffer
    #: app (spec secret "Hold a secret for a new destination until a
    #: person approves it").
    APPROVAL_PENDING = 9
    #: The daemon is running but waits in its setup state for git (spec daemon
    #: "Wait in a setup state when git is missing or too old").
    GIT_NEEDED = 10
    #: The person cancelled, failed or did not answer the presence check; the
    #: approval stays pending (spec secret "Approve from the command line with
    #: the person's own presence check").
    PRESENCE_NOT_CONFIRMED = 11
    #: The desktop app is not running and could not be started here.
    APP_UNAVAILABLE = 12
    #: An operation started with ``--wait`` had not finished by ``--timeout``.
    WAIT_TIMEOUT = 13
