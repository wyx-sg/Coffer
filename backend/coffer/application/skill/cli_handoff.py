"""The hand-off prompt for a required command that needs the person (spec
skill-manager "Hand a required command to an agent with a prompt").

Coffer does not install anything: a command that is missing or too old is
handed to the person's agent, which chooses the install method that suits this
machine, and ends by asking Coffer to check the command again, so the CLIs page
and the Overview clear without the person pressing Check. The facts are the command,
what Coffer itself runs it for, the skills that need it with the minimum each
asked for, the MCP servers started with it, what was found, and the machine;
``domain/handoff.py`` adds the rules every hand-off carries.
"""

from __future__ import annotations

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


def coffer_uses(row: RequiredCommand) -> str:
    """What Coffer itself runs the command for, as a phrase after "to"
    ("keep the vault's history and to sync the vault")."""
    return " and to ".join(_COFFER_USES[u] for u in row.needed_by_coffer)


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
        facts.append(f"Coffer itself uses it to {coffer_uses(row)}.")
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
    # Not ``<command> --version``: some tools (``go``, ``kubectl``) take no
    # such flag, and the agent knows how to confirm the tool it installed.
    verify = (
        f"When you are done, confirm `{row.command}` works, then run "
        f"`coffer cli check {row.command}` so Coffer sees it."
    )
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
    return None


__all__ = ["cli_handoff"]
