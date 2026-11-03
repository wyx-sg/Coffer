"""How long the CLI waits for the daemon's answer.

ADR ``cli-request-wait-budgets``. Connecting is quick or the daemon is not
there, so it has its own short limit. Waiting for the answer depends on the
operation: an ordinary command answers in well under a second, so a short wait
still catches a daemon that stopped answering; a command whose route reaches
the network or runs git declares a longer wait (``RouteCommand.wait``), a
little past the deadline the daemon itself holds that operation to, so the
answer is the daemon's own specific error rather than the CLI giving up first.
``coffer --request-timeout <seconds>`` replaces the wait for one command.
"""

from __future__ import annotations

import httpx

#: Connecting to the daemon on this machine.
CONNECT_S = 5.0
#: An ordinary command: no network, no subprocess.
QUICK_S = 15.0
#: A route that makes one call out (a provider, an MCP server, a platform's
#: API, a CLI's version probe); the daemon bounds those at 60 s or less.
NETWORK_S = 90.0
#: A route that runs git over the network: a skill's Git source (the daemon
#: holds one operation to 300 s, ``GIT_OPERATION_DEADLINE_S``) or a vault sync
#: round (each git network call 120 s).
GIT_S = 330.0

_override: float | None = None


def set_override(seconds: float | None) -> None:
    """``coffer --request-timeout``: the wait for every request of this command."""
    global _override
    _override = seconds


def wait_for(declared: float | None) -> float:
    """The wait for one request: the override, else what it declares, else quick."""
    if _override is not None:
        return _override
    return declared if declared is not None else QUICK_S


def timeout(declared: float | None = None) -> httpx.Timeout:
    return httpx.Timeout(wait_for(declared), connect=min(CONNECT_S, wait_for(declared)))


__all__ = ["CONNECT_S", "GIT_S", "NETWORK_S", "QUICK_S", "set_override", "timeout", "wait_for"]
