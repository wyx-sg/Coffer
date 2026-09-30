"""What an MCP server's page says about its state.

Spec mcp-gateway "Explain a server's state on its page".

Pure over what is already persisted — the invocation log, the health record a
test wrote, and whether each credential the config cites is stored — so the
page's status read never spawns anything:

- **failure detail**: the newest run of calls that failed to reach the server
  (a transport error or a timeout; ``denied`` rows never reached it and are
  skipped, and a call the upstream answered with an error — or one that
  succeeded — ends the run). Its newest row gives the last error and when it
  happened, its oldest when the server started failing.
- **last success**: when the newest successful call was, and which capability.
- **missing secret**: the first credential the transport cites whose value is
  not in this machine's store (a vault restored on a new Mac), by the
  environment or header key that cites it and the reference itself. The value
  is never read.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from coffer.application.mcp.invocation_outcome import is_upstream_answered
from coffer.domain.mcp.capability import MCPInvocation


@dataclass(frozen=True)
class FailureRun:
    last_error: str | None
    last_error_at: datetime
    failing_since: datetime


def failure_run(recent: Iterable[MCPInvocation]) -> FailureRun | None:
    """The newest run of transport failures in ``recent`` (newest first), if any."""
    run: list[MCPInvocation] = []
    for inv in recent:
        if inv.status == "denied":
            continue
        if inv.status == "ok" or is_upstream_answered(inv):
            break
        run.append(inv)
    if not run:
        return None
    return FailureRun(
        last_error=run[0].error_message,
        last_error_at=run[0].timestamp,
        failing_since=run[-1].timestamp,
    )


def credential_refs_of(config: Mapping[str, Any]) -> dict[str, str]:
    """The ``{env or header key: credential ref}`` map a server's transport cites."""
    transport = config.get("transport")
    if not isinstance(transport, Mapping):
        return {}
    refs = transport.get("credential_refs")
    if not isinstance(refs, Mapping):
        return {}
    return {str(k): str(v) for k, v in refs.items() if isinstance(v, str) and v}


def missing_secret(
    config: Mapping[str, Any], exists: Callable[[str], bool]
) -> tuple[str, str] | None:
    """``(key, ref)`` of the first cited credential with no stored value, or None.

    ``exists`` is asked only when the config cites something, so a server with
    no secrets never touches the store.
    """
    for key, ref in credential_refs_of(config).items():
        if not exists(ref):
            return key, ref
    return None


__all__ = ["FailureRun", "credential_refs_of", "failure_run", "missing_secret"]
