"""Shared CLI options + exit code conventions.

Exit codes match the convention in agents/workflow.md / the rest of the
CLI surface: 0 success, 1 generic, 2 invalid usage (Typer's default),
3 daemon unreachable, 4 not found, 5 conflict, 6 invalid input,
7 upstream test failed, 8 credential issue.
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
    CREDENTIAL_ISSUE = 8
