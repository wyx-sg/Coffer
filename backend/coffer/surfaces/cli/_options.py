"""Shared CLI options + exit code conventions.

Exit codes match the convention in .agents/workflow.md / the rest of the
CLI surface: 0 success, 1 generic, 2 invalid usage (Typer's default),
3 daemon unreachable, 4 not found, 5 conflict, 6 invalid input,
7 upstream test failed, 8 secret issue, 9 approval pending, 10 the daemon
waits for git.
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
