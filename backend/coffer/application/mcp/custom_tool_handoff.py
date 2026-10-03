"""The hand-off prompts for a custom tool group that cannot reach its API.

Two problems depend on this machine (DNS, VPN or proxy, firewall, the API being
down), so Coffer hands them to the person's agent instead of guessing a fix
(spec mcp-gateway "Hand a failing custom tool group to an agent"):

* a test run of a request that could not connect or timed out;
* a group whose last call failed.

A prompt carries the group's name, the request's method and URL, the error
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


def request_test_handoff(
    *,
    group: str | None,
    method: str,
    url: str | None,
    failure: str,
    error: str | None,
    seconds: int | None,
    machine: str,
) -> str:
    """The prompt for a test run that could not connect (``failure`` ``connect``) or timed out."""
    what = (
        "timed out" + (f" after {seconds} s" if seconds else "") + " with no response"
        if failure == "timeout"
        else "could not connect"
    )
    where = f"{method} {redacted_url(url)}" if url else method
    facts = [
        f"The custom tool group is {f'named {group} in Coffer' if group else 'not saved yet'}.",
        f"Testing a request {what}: {where}.",
        _error_fact(error if failure == "connect" else None),
        f"This machine: {machine}.",
    ]
    return render_handoff(
        Handoff(
            task=(
                "Please find out why a test request of a Coffer custom tool group could not "
                "reach its API, and propose a fix."
            ),
            facts=tuple(f for f in facts if f),
            steps=(_CHECKS,),
        )
    )


def failing_group_handoff(
    *, group: str, base_url: str, status: str | None, error: str | None, machine: str
) -> str:
    """The prompt for a group whose last call failed: the status and error of that call."""
    facts = [
        f"The custom tool group is named {group} in Coffer; its base URL is "
        f"{redacted_url(base_url)}.",
        "Its last call "
        + ("timed out." if status == "timeout" else "got an error from the API or the network."),
        _error_fact(error),
        f"This machine: {machine}.",
    ]
    return render_handoff(
        Handoff(
            task=(
                f"Please find out why the calls of Coffer's custom tool group {group} fail, "
                "and propose a fix."
            ),
            facts=tuple(f for f in facts if f),
            steps=(_CHECKS,),
        )
    )


__all__ = ["failing_group_handoff", "request_test_handoff"]
