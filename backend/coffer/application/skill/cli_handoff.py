"""The hand-off prompt for a required command that needs the person (spec
skill-manager "Hand a required command to an agent with a prompt").

Coffer does not install anything: a command that is missing or too old is
handed to the person's agent, which chooses the install method that suits this
machine. A command that is installed but not logged in is handed over only for
help logging in — the person logs in themselves. The facts are the command,
what Coffer itself runs it for, the skills that need it with the minimum each
asked for, the MCP servers started with it, what was found, and the machine;
``domain/handoff.py`` adds the rules every hand-off carries.
"""

from __future__ import annotations

import shlex

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.skill.cli_status import (
    CliStatus,
    CofferUse,
    NeededBy,
    ProbeResult,
    RequiredCommand,
)

_COFFER_USES: dict[CofferUse, str] = {
    CofferUse.VAULT_HISTORY: "keep the vault's history",
    CofferUse.SYNC: "sync the vault",
}


def _named(row: RequiredCommand) -> str:
    return f"`{row.command}` ({row.title})" if row.title else f"`{row.command}`"


def _needed_by(row: RequiredCommand) -> tuple[str, ...]:
    def one(need: NeededBy) -> str:
        return (
            f"{need.skill_name} (version {need.min_version} or newer)"
            if need.min_version
            else need.skill_name
        )

    facts: list[str] = []
    if row.needed_by_coffer:
        uses = " and to ".join(_COFFER_USES[u] for u in row.needed_by_coffer)
        facts.append(f"Coffer itself uses it to {uses}.")
    if row.needed_by:
        facts.append(
            "Needed by the Coffer skills: " + ", ".join(one(n) for n in row.needed_by) + "."
        )
    if row.needed_by_servers:
        servers = ", ".join(
            f"{s.server_name} (started with `{s.launcher}`)" for s in row.needed_by_servers
        )
        facts.append(f"Needed by the MCP servers Coffer starts: {servers}.")
    return tuple(facts)


def cli_handoff(
    row: RequiredCommand, probe: ProbeResult, status: CliStatus, machine: str
) -> str | None:
    """The prompt for ``row`` in ``status``; ``None`` for a ready command."""
    verify = f"When you are done, run `{row.command} --version` to confirm it works."
    this_machine = f"This machine: {machine}."
    if status is CliStatus.MISSING:
        return render_handoff(
            Handoff(
                task=f"Please install the command-line tool {_named(row)} on this machine.",
                facts=(*_needed_by(row), this_machine),
                steps=("Choose the right install method for this machine.", verify),
            )
        )
    if status is CliStatus.OUTDATED:
        return render_handoff(
            Handoff(
                task=f"Please update the command-line tool {_named(row)} on this machine.",
                facts=(
                    f"Installed: {probe.version} at {probe.path}; version {row.min_version} "
                    "or newer is needed.",
                    *_needed_by(row),
                    this_machine,
                ),
                steps=(
                    "Update it the same way it was installed, or choose the right method "
                    "for this machine.",
                    verify,
                ),
            )
        )
    if status is CliStatus.LOGGED_OUT:
        facts = [
            f"It is installed at {probe.path}, but `{shlex.join(row.login_check or ())}` "
            "says I am not logged in.",
        ]
        if row.login:
            facts.append(f"The skills suggest logging in with `{row.login}`.")
        facts += [*_needed_by(row), this_machine]
        return render_handoff(
            Handoff(
                task=f"Please help me log in to the command-line tool {_named(row)}.",
                facts=tuple(facts),
                steps=(
                    "Tell me the command to run and what to expect; I will run it and enter "
                    "anything it asks for myself.",
                    f"Afterwards, run `{shlex.join(row.login_check or ())}` to confirm.",
                ),
            )
        )
    return None


__all__ = ["cli_handoff"]
