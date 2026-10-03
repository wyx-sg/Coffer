"""Wire shapes of ``/api/v1/clis/{command}/interface`` (spec skill-manager
"Serve required commands on REST and the web")."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from coffer.domain.skill.cli_help import HelpNode, Interface

CliInterfaceStatusOut = Literal["not_read", "ok", "unavailable", "no_help"]


class CliHelpSubcommandOut(BaseModel):
    name: str
    summary: str | None


class CliHelpOptionOut(BaseModel):
    #: Every spelling, as printed: ``["-o", "--output"]``.
    names: list[str]
    metavar: str | None
    description: str | None
    default: str | None
    required: bool


class CliHelpArgumentOut(BaseModel):
    name: str
    description: str | None
    required: bool


class CliHelpNodeOut(BaseModel):
    """One command of the tool: the tool itself (empty ``path``) or a
    subcommand. ``raw`` is the help as the tool printed it."""

    path: list[str]
    usage: str | None
    description: str | None
    subcommands: list[CliHelpSubcommandOut]
    options: list[CliHelpOptionOut]
    arguments: list[CliHelpArgumentOut]
    raw: str
    #: Whether anything of ``raw`` was recognised as usage, subcommands,
    #: options or arguments.
    structured: bool
    #: Why this command has no help (timed out, printed nothing).
    error: str | None
    #: ``raw`` was cut at the size cap.
    truncated: bool


class CliInterfaceOut(BaseModel):
    """``not_read`` carries no nodes: nothing has been run for this version of
    the tool yet (a GET never runs it; POST reads it)."""

    status: CliInterfaceStatusOut
    message: str | None
    version: str | None
    discovered_at: datetime | None
    #: The tree was cut by the depth, node or time bound.
    incomplete: bool
    nodes: list[CliHelpNodeOut]


def _node_out(n: HelpNode) -> CliHelpNodeOut:
    return CliHelpNodeOut(
        path=list(n.path),
        usage=n.usage,
        description=n.description,
        subcommands=[CliHelpSubcommandOut(name=s.name, summary=s.summary) for s in n.subcommands],
        options=[
            CliHelpOptionOut(
                names=list(o.names),
                metavar=o.metavar,
                description=o.description,
                default=o.default,
                required=o.required,
            )
            for o in n.options
        ],
        arguments=[
            CliHelpArgumentOut(name=a.name, description=a.description, required=a.required)
            for a in n.arguments
        ],
        raw=n.raw,
        structured=n.structured,
        error=n.error,
        truncated=n.truncated,
    )


def cli_interface_out(i: Interface) -> CliInterfaceOut:
    return CliInterfaceOut(
        status=i.status.value,
        message=i.message,
        version=i.version,
        discovered_at=i.discovered_at,
        incomplete=i.incomplete,
        nodes=[_node_out(n) for n in i.nodes],
    )
