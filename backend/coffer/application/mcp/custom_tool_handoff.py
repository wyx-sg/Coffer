"""The hand-off prompts for a custom tool group that cannot reach its API.

Why a group cannot reach its API depends on this machine (DNS, VPN or proxy,
firewall, the API being down), so Coffer hands it to the person's agent
instead of guessing a fix (spec mcp-gateway "Hand a failing custom tool group
to an agent"). One prompt serves a test run of a request that could not
connect or timed out and a group whose last call failed.

It carries the group's name, the request's method and URL, the error
text and the machine — the URL's credentials and secret-looking query values,
and anything secret-looking in the error, read ``<secret>``
(``domain/mcp/config_summary``). Header values are never mentioned. The
machine label is passed in by the caller.
"""

from __future__ import annotations

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.mcp.config_summary import redacted_url, scrub

#: A quoted error longer than this is cut.
_ERROR_MAX = 300
_CHECKS = (
    "Find out why from this machine: check that the host resolves and is reachable (VPN, proxy, "
    "DNS, firewall), that the API is up and not slow, and what the recent calls returned "
    "(`coffer log mcp`). Tell me what you find before changing anything."
)


def _error_fact(error: str | None) -> str | None:
    return f"The error: {scrub(error)[:_ERROR_MAX]}." if error else None


def group_handoff(
    *,
    group: str | None,
    request: str,
    outcome: str,
    error: str | None,
    machine: str,
) -> str:
    """The one prompt for a custom tool group that cannot reach its API.

    ``request`` is what was sent (``GET <url>`` for a test, the base URL for
    the group's last call) and ``outcome`` how it ended (``timed out after
    30 s``, ``could not connect``); both are redacted here. A test of an unsaved
    group has no ``group`` name."""
    facts = [
        f"The custom tool group is {f'named {group} in Coffer' if group else 'not saved yet'}.",
        f"A request {outcome}: {request}.",
        _error_fact(error),
        f"This machine: {machine}.",
    ]
    task = (
        f"Please find out why the calls of Coffer's custom tool group {group} fail, "
        "and propose a fix."
        if group
        else "Please find out why a test request of a Coffer custom tool group could not "
        "reach its API, and propose a fix."
    )
    return render_handoff(Handoff(task=task, facts=tuple(f for f in facts if f), steps=(_CHECKS,)))


def test_request(method: str, url: str | None) -> str:
    """A tested request as the prompt names it, credentials redacted."""
    return f"{method} {redacted_url(url)}" if url else method


def test_outcome(failure: str, seconds: int | None) -> str:
    if failure == "timeout":
        return "timed out" + (f" after {seconds} s" if seconds else "") + " with no response"
    return "could not connect"


def call_outcome(status: str | None) -> str:
    return "timed out" if status == "timeout" else "got an error from the API or the network"


__all__ = ["call_outcome", "group_handoff", "test_outcome", "test_request"]
