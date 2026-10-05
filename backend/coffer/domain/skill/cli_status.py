"""One row per required command, and what state it is in.

Rows aggregate every managed skill that declares the command and the tool the
person added by hand under that name (``DeclaredTool``; no skill needed): the
minimum is the highest any of them asks for; the title and login check come
from the hand-added declaration first, then from the first skill (by name) that
declares each, and the login command from the first skill that gives one. The launcher an
enabled stdio MCP server starts with is required too — by that server, under
the command that provides it (``uv`` for ``uvx``, see :func:`launcher_cli`),
with no minimum and no login. The commands Coffer runs itself
(:data:`COFFER_NEEDS`: ``git`` for the vault's history and sync) are required
by Coffer, so they are listed even when no skill or server asks. The status is
problem-first — ``missing``, ``outdated``, ``logged_out``, ``ready`` — and a
version that cannot be read is reported as unknown, never as outdated.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from coffer.domain.skill.cli_declared import DeclaredTool
from coffer.domain.skill.requirements import CommandRequirement
from coffer.domain.versions import at_least, compare_versions


class CliStatus(StrEnum):
    MISSING = "missing"
    OUTDATED = "outdated"
    LOGGED_OUT = "logged_out"
    READY = "ready"


#: Problem-first order for lists.
STATUS_ORDER: dict[CliStatus, int] = {s: i for i, s in enumerate(CliStatus)}


class LoginState(StrEnum):
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    #: The command declares no login check.
    NOT_NEEDED = "not_needed"


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
    min_version: str | None
    why: str | None


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
    min_version: str | None
    login_check: tuple[str, ...] | None
    login: str | None
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
    """What checking the command found. ``login`` is ``None`` when the command
    was not found, so its login check could not run, or when it declares one
    that has not been run (only a Check runs it)."""

    path: str | None
    version: str | None
    login: LoginState | None
    checked_at: datetime
    #: The login check that produced ``login`` — a changed declaration is
    #: probed again rather than served from the cache.
    login_check: tuple[str, ...] | None = None


def aggregate(
    skills: Iterable[SkillRequirements],
    servers: Iterable[ServerLauncher] = (),
    declared: Iterable[DeclaredTool] = (),
    coffer: Iterable[CofferNeed] = (),
    notes: Mapping[str, str] | None = None,
) -> list[RequiredCommand]:
    """One :class:`RequiredCommand` per command, sorted by command name.
    ``notes`` are descriptions written for tools nobody added by hand; a
    hand-added tool's own description wins."""
    notes = notes or {}
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
) -> RequiredCommand:
    reqs = [req for _uid, _name, req in entries]
    own = declared or DeclaredTool(command)
    return RequiredCommand(
        command=command,
        title=own.title
        or (coffer.title if coffer else None)
        or next((r.title for r in reqs if r.title), None),
        min_version=highest_minimum([own.min_version, *(r.min_version for r in reqs)]),
        login_check=own.login_check or next((r.login_check for r in reqs if r.login_check), None),
        login=next((r.login for r in reqs if r.login), None),
        needed_by=tuple(
            NeededBy(skill_uid=uid, skill_name=name, min_version=r.min_version, why=r.why)
            for uid, name, r in entries
        ),
        needed_by_servers=tuple(servers),
        added=declared is not None,
        description=own.description or note,
        needed_by_coffer=coffer.uses if coffer else (),
    )


def highest_minimum(minimums: Iterable[str | None]) -> str | None:
    best: str | None = None
    for candidate in minimums:
        if candidate is None:
            continue
        if best is None or (compare_versions(candidate, best) or 0) > 0:
            best = candidate
    return best


def status_of(required: RequiredCommand, probe: ProbeResult) -> CliStatus:
    if probe.path is None:
        return CliStatus.MISSING
    if (
        required.min_version is not None
        and probe.version is not None
        and at_least(probe.version, required.min_version) is False
    ):
        return CliStatus.OUTDATED
    if probe.login is LoginState.LOGGED_OUT:
        return CliStatus.LOGGED_OUT
    return CliStatus.READY


def login_state(required_check: tuple[str, ...] | None, ok: bool | None) -> LoginState:
    """``ok`` is the login check's answer: ``True`` for exit 0, ``False`` for
    any other exit, ``None`` for one that could not run or timed out."""
    if required_check is None:
        return LoginState.NOT_NEEDED
    return LoginState.LOGGED_IN if ok else LoginState.LOGGED_OUT


__all__ = [
    "COFFER_NEEDS",
    "STATUS_ORDER",
    "CliStatus",
    "CofferNeed",
    "CofferUse",
    "LoginState",
    "NeededBy",
    "ProbeResult",
    "RequiredCommand",
    "ServerLauncher",
    "SkillRequirements",
    "aggregate",
    "highest_minimum",
    "launcher_cli",
    "login_state",
    "status_of",
]
