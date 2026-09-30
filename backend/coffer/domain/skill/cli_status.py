"""One row per required command, and what state it is in.

Rows aggregate every managed skill that declares the command: the minimum is
the highest any of them asks for; the title, login check and login command
come from the first skill (by name) that declares each. The status is
problem-first — ``missing``, ``outdated``, ``logged_out``, ``ready`` — and a
version that cannot be read is reported as unknown, never as outdated.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

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
class RequiredCommand:
    command: str
    title: str | None
    min_version: str | None
    login_check: tuple[str, ...] | None
    login: str | None
    needed_by: tuple[NeededBy, ...]


@dataclass(frozen=True)
class ProbeResult:
    """What checking the command found. ``login`` is ``None`` when the command
    was not found, so its login check could not run."""

    path: str | None
    version: str | None
    login: LoginState | None
    checked_at: datetime
    #: The login check that produced ``login`` — a changed declaration is
    #: probed again rather than served from the cache.
    login_check: tuple[str, ...] | None = None


def aggregate(skills: Iterable[SkillRequirements]) -> list[RequiredCommand]:
    """One :class:`RequiredCommand` per command, sorted by command name."""
    by_command: dict[str, list[tuple[str, str, CommandRequirement]]] = {}
    for skill in sorted(skills, key=lambda s: (s.skill_name, s.skill_uid)):
        for req in skill.requirements:
            by_command.setdefault(req.command, []).append((skill.skill_uid, skill.skill_name, req))
    return [_row(command, entries) for command, entries in sorted(by_command.items())]


def _row(command: str, entries: Sequence[tuple[str, str, CommandRequirement]]) -> RequiredCommand:
    reqs = [req for _uid, _name, req in entries]
    return RequiredCommand(
        command=command,
        title=next((r.title for r in reqs if r.title), None),
        min_version=highest_minimum(r.min_version for r in reqs),
        login_check=next((r.login_check for r in reqs if r.login_check), None),
        login=next((r.login for r in reqs if r.login), None),
        needed_by=tuple(
            NeededBy(skill_uid=uid, skill_name=name, min_version=r.min_version, why=r.why)
            for uid, name, r in entries
        ),
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
    "STATUS_ORDER",
    "CliStatus",
    "LoginState",
    "NeededBy",
    "ProbeResult",
    "RequiredCommand",
    "SkillRequirements",
    "aggregate",
    "highest_minimum",
    "login_state",
    "status_of",
]
