"""The hand-off prompts for an MCP server that will not start or answer.

One prompt per server, for the chore that depends on the machine, so Coffer
hands it to the person's agent instead of naming a package-manager command
(Principle IV): install the server's launcher (``npx``, ``uvx``, ``docker``…)
when it is not found here (spec mcp-gateway "Name a missing stdio launcher"),
else find why the server or its test fails (spec mcp-gateway "Hand a failing
MCP server's diagnosis to an agent").

The prompt carries only what Coffer already knows: the server's name, its
config with every value that could be a secret left out
(``domain/mcp/config_summary``), the machine, and for a failure the error and
the last lines the server printed. The machine label and ``PATH`` are passed
in by the caller (application code does not read the host). The same text is
what the server page, the Overview's attention row hand over.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.mcp.config_summary import command_line_of, config_summary, scrub

#: How many of the server's newest stderr lines a diagnosis prompt quotes.
STDERR_LINES = 20
#: A quoted line longer than this is cut.
_LINE_MAX = 300


def _test_command(name: str) -> str:
    return f"coffer mcp test {name}"


def _machine(machine: str) -> str:
    return f"This machine: {machine}."


def _verify_step(name: str, saved: bool) -> str:
    """How the fix is checked: a saved server by the CLI, an unsaved config
    (the Add / Edit dialog's test) by pressing Test there again."""
    if saved:
        return f"Verify the fix with `{_test_command(name)}`."
    return (
        "Then tell me to press Test again in Coffer's server dialog — this config is not "
        "saved yet, so the CLI cannot test it."
    )


def _stderr_fact(lines: Sequence[str]) -> str | None:
    kept = [scrub(line.rstrip())[:_LINE_MAX] for line in lines if line.strip()]
    kept = kept[-STDERR_LINES:]
    if not kept:
        return None
    return "Its last lines on stderr, oldest first:\n" + "\n".join(f"    {line}" for line in kept)


def server_handoff(
    *,
    name: str,
    config: Mapping[str, Any],
    error: str | None,
    stderr: Sequence[str],
    machine: str,
    log_path: str | None = None,
    saved: bool = True,
    runner: str | None = None,
    path: str = "",
) -> str:
    """The one prompt for an MCP server that will not start or answer.

    With ``runner`` (its launcher is not found on this machine) the task is
    installing it, which is the cause of any failure; otherwise it is finding
    why the server fails. Either way the prompt carries the newest real error.
    ``stderr`` is oldest first; only the newest :data:`STDERR_LINES` are kept,
    and every quoted line and the error pass through
    :func:`~coffer.domain.mcp.config_summary.scrub`."""
    facts: list[str] = [
        f"The MCP server is named {name} in Coffer."
        if saved
        else f"The MCP server is being set up in Coffer as {name}; it is not saved yet.",
        *config_summary(config),
    ]
    if runner is not None:
        command = command_line_of(config) or runner
        facts += [
            f"Coffer starts it as `{command}`.",
            f"`{runner}` isn't found on this machine; Coffer looks it up on this PATH: "
            f"{path or '(empty)'}.",
            "Coffer may run as a process started from the GUI, which does not read the "
            "shell's startup files, so a tool only a login shell can find is not found.",
        ]
    if error:
        facts.append(f"The last error: {scrub(error)[:_LINE_MAX]}")
    elif runner is None:
        facts.append("Its last connection test failed.")
    tail = _stderr_fact(stderr)
    if tail:
        facts.append(tail)
    if log_path:
        facts.append(f"Its full log: {log_path}.")
    facts.append(_machine(machine))
    if runner is not None:
        task = (
            f"Please install `{runner}` on this machine so Coffer can start the MCP server {name}."
        )
        steps: tuple[str, ...] = (
            "Install it the way that fits this machine, so that a process started from "
            "the GUI can find it (in one of the PATH directories above).",
            _verify_step(name, saved),
        )
    else:
        task = (
            f"Please find out why the MCP server {name}, which Coffer runs for my agents, "
            "fails, and propose a fix."
        )
        steps = (
            "Find the cause — for example a missing environment variable, a wrong path, "
            "a package that won't start, the server being down, or a network or proxy "
            "problem — and tell me the fix before you change anything.",
            "Do not read or change the secrets Coffer stores for this server; if one is "
            "wrong, tell me and I will replace it on the server's page.",
            _verify_step(name, saved),
        )
    return render_handoff(Handoff(task=task, facts=tuple(facts), steps=steps))


__all__ = ["STDERR_LINES", "server_handoff"]
