"""One row per required command, and what state it is in.

Rows aggregate every managed skill that declares the command and the tool the
person added by hand under that name (``DeclaredTool``; no skill needed): the
title comes from the
hand-added declaration (or, for a tool nobody added, the person's edits) first,
then from the first skill (by name) that declares one. The launcher an
enabled stdio MCP server starts with is required too — by that server, under
the command that provides it (``uv`` for ``uvx``, see :func:`launcher_cli`),
The commands Coffer runs itself
(:data:`COFFER_NEEDS`: ``git`` for the vault's history and sync) are required
by Coffer, so they are listed even when no skill or server asks. The status is
problem-first — ``missing``, then ``ready``. Coffer runs none of the commands it
checks: it only looks each one up on ``PATH``. Whether a tool is new enough or
logged in, the agent that uses it finds out itself (ADR
agents-check-cli-logins-themselves).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from coffer.domain.skill.cli_declared import DeclaredTool
from coffer.domain.skill.requirements import CommandRequirement


class CliStatus(StrEnum):
    MISSING = "missing"
    READY = "ready"


#: Problem-first order for lists.
STATUS_ORDER: dict[CliStatus, int] = {s: i for i, s in enumerate(CliStatus)}


@dataclass(frozen=True)
class SkillRequirements:
    """What one managed skill declares, read from its master SKILL.md."""

    skill_uid: str
    skill_name: str
    requirements: tuple[CommandRequirement, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class NeededBy:
    skill_uid: str
    skill_name: str
    why: str | None
    #: Profiles that declared it; empty when SKILL.md itself did.
    profiles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServerLauncher:
    """An enabled stdio MCP server and the launcher it is started with."""

    server_uid: str
    server_name: str
    launcher: str


@dataclass(frozen=True)
class RequiredCommand:
    command: str
    title: str | None
    needed_by: tuple[NeededBy, ...]
    #: The MCP servers started with this command (or a launcher it provides).
    needed_by_servers: tuple[ServerLauncher, ...] = ()
    #: The person added this command by hand.
    added: bool = False
    description: str | None = None
    #: What Coffer itself runs the command for; empty when Coffer does not.
    needed_by_coffer: tuple[CofferUse, ...] = ()


class CofferUse(StrEnum):
    """What Coffer itself runs a command for."""

    VAULT_HISTORY = "vault_history"
    SYNC = "sync"


@dataclass(frozen=True)
class CofferNeed:
    """A command Coffer itself runs, and what for."""

    command: str
    title: str | None
    uses: tuple[CofferUse, ...]


#: The commands Coffer itself needs on this machine.
COFFER_NEEDS: tuple[CofferNeed, ...] = (
    CofferNeed("git", "Git", (CofferUse.VAULT_HISTORY, CofferUse.SYNC)),
)


#: Launchers that ship inside another command: checking the CLI checks them.
_PROVIDED_BY: dict[str, str] = {"uvx": "uv", "npx": "node", "bunx": "bun"}


def launcher_cli(launcher: str) -> str | None:
    """The command a stdio launcher is checked as — ``uv`` for ``uvx``,
    ``node`` for ``npx``, the launcher itself otherwise. ``None`` for a path
    (``./run.sh``, ``/opt/x/bin/server``): that is a file, not a command on
    ``PATH``."""
    name = launcher.strip()
    if not name or "/" in name or "\\" in name:
        return None
    return _PROVIDED_BY.get(name, name)


@dataclass(frozen=True)
class ProbeResult:
    """What looking the command up found: where it is (``None``: not on
    ``PATH``)."""

    path: str | None
    checked_at: datetime


def aggregate(
    skills: Iterable[SkillRequirements],
    servers: Iterable[ServerLauncher] = (),
    declared: Iterable[DeclaredTool] = (),
    coffer: Iterable[CofferNeed] = (),
    notes: Mapping[str, str] | None = None,
    edits: Mapping[str, DeclaredTool] | None = None,
) -> list[RequiredCommand]:
    """One :class:`RequiredCommand` per command, sorted by command name.
    ``notes`` are descriptions written for tools nobody added by hand; a
    hand-added tool's own description wins. ``edits`` are the display name
    changed on such a tool: it takes the place of a
    hand-added declaration's, and list no command on their own."""
    notes = notes or {}
    edits = edits or {}
    by_declared = {d.command: d for d in declared}
    by_coffer = {c.command: c for c in coffer}
    by_command: dict[str, list[tuple[str, str, CommandRequirement]]] = {}
    for skill in sorted(skills, key=lambda s: (s.skill_name, s.skill_uid)):
        for req in skill.requirements:
            by_command.setdefault(req.command, []).append((skill.skill_uid, skill.skill_name, req))
    by_server: dict[str, list[ServerLauncher]] = {}
    for server in sorted(servers, key=lambda s: (s.server_name, s.server_uid)):
        cli = launcher_cli(server.launcher)
        if cli is not None:
            by_server.setdefault(cli, []).append(server)
    return [
        _row(
            command,
            by_command.get(command, ()),
            by_server.get(command, ()),
            by_declared.get(command),
            by_coffer.get(command),
            notes.get(command),
            edits.get(command),
        )
        for command in sorted(
            by_command.keys() | by_server.keys() | by_declared.keys() | by_coffer.keys()
        )
    ]


def _row(
    command: str,
    entries: Sequence[tuple[str, str, CommandRequirement]],
    servers: Sequence[ServerLauncher] = (),
    declared: DeclaredTool | None = None,
    coffer: CofferNeed | None = None,
    note: str | None = None,
    edit: DeclaredTool | None = None,
) -> RequiredCommand:
    reqs = [req for _uid, _name, req in entries]
    own = declared or edit or DeclaredTool(command)
    return RequiredCommand(
        command=command,
        title=own.title
        or (coffer.title if coffer else None)
        or next((r.title for r in reqs if r.title), None),
        needed_by=tuple(
            NeededBy(
                skill_uid=uid,
                skill_name=name,
                why=r.why,
                profiles=r.profiles,
            )
            for uid, name, r in entries
        ),
        needed_by_servers=tuple(servers),
        added=declared is not None,
        description=own.description or note,
        needed_by_coffer=coffer.uses if coffer else (),
    )


def status_of(probe: ProbeResult) -> CliStatus:
    return CliStatus.MISSING if probe.path is None else CliStatus.READY


__all__ = [
    "COFFER_NEEDS",
    "STATUS_ORDER",
    "CliStatus",
    "CofferNeed",
    "CofferUse",
    "NeededBy",
    "ProbeResult",
    "RequiredCommand",
    "ServerLauncher",
    "SkillRequirements",
    "aggregate",
    "launcher_cli",
    "status_of",
]
