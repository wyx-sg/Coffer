"""The hand-off for a daemon log error that is about the environment.

An ERROR record in ``daemon.log`` is Coffer's own bug or something outside it —
an external service that refused the connection, a name that would not resolve,
a file the process may not read. Only the second kind is a chore for the
person's agent (principle "Button, hand-off or sentence": the fix is outside
Coffer, on this machine); a Coffer-internal error offers only "Copy record"
(spec web-ui "Hand an environment error to an agent"). The prompt carries the
logger, the message and the traceback, scrubbed of anything that looks like a
secret (``domain/mcp/config_summary.scrub``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from coffer.application.log_reader import normalise_level
from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.mcp.config_summary import scrub

#: Wording that says the failure came from outside Coffer: the network, a
#: missing or unreadable file, a launcher that is not installed.
_ENVIRONMENT = re.compile(
    r"ConnectError|ConnectTimeout|ReadTimeout|TimeoutError|timed? ?out|connection "
    r"(?:refused|reset|aborted|closed)|name or service not known|getaddrinfo|"
    r"SSLError|certificate verify|\[Errno \d+\]|ECONN\w+|ENOENT|EACCES|FileNotFoundError|"
    r"PermissionError|permission denied|no such file|command not found|"
    r"failed to start|unreachable|proxy",
    re.IGNORECASE,
)

#: A quoted line longer than this is cut; a traceback longer than this many lines keeps its tail.
_LINE_MAX = 300
_TRACEBACK_LINES = 40


def is_environment_error(
    level: str | None, message: str | None, continuation: Sequence[str]
) -> bool:
    """Whether this record is an error whose cause lies outside Coffer."""
    if normalise_level(level or "") not in {"error", "critical"}:
        return False
    return bool(_ENVIRONMENT.search("\n".join([message or "", *continuation])))


def daemon_error_handoff(
    *,
    logger: str | None,
    message: str | None,
    continuation: Sequence[str],
    machine: str,
) -> str:
    """The prompt to find why one daemon error happened and propose a fix."""
    facts = [
        f"Logger: {logger or '(none)'}.",
        f"Message: {scrub(message or '')[:_LINE_MAX]}",
    ]
    lines = [scrub(line.rstrip())[:_LINE_MAX] for line in continuation if line.strip()]
    if lines:
        facts.append(
            "Traceback, oldest first:\n"
            + "\n".join(f"    {line}" for line in lines[-_TRACEBACK_LINES:])
        )
    facts.append(f"This machine: {machine}.")
    return render_handoff(
        Handoff(
            task=(
                "Please find out why Coffer's daemon logged this error, which looks like a "
                "problem with something outside Coffer, and propose a fix."
            ),
            facts=tuple(facts),
            steps=(
                "Find the cause — for example a service that is down, a network or proxy "
                "problem, or a file or program this machine cannot reach — and tell me the fix "
                "before you change anything.",
                "Coffer's own log is `coffer log daemon`; read it only if you need more "
                "context around this record.",
            ),
        )
    )


__all__ = ["daemon_error_handoff", "is_environment_error"]
