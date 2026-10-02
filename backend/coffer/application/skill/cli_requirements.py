"""The command-line tools Coffer knows: the ones managed skills and MCP servers
require and the ones the person added by hand; read, checked, handed off.

``CliRequirementService`` reads every managed skill's master SKILL.md at check
time (so an edit made in the user's editor is picked up by the next read), the
launcher of every enabled stdio MCP server (``McpLaunchersPort``, supplied
by the composition root) and the tools added by hand
(``DeclaredToolsPort``), aggregates one row per command
(``domain/skill/cli_status.py``), and probes
each command through a :class:`CommandProbePort` in a worker thread. Results
are cached per command until the user asks to check again or the daemon
restarts; a command no result is cached for is probed on the read that first
needs it.

Coffer installs nothing. A command that needs the person carries a hand-off
prompt for their agent (``cli_handoff.py``; spec skill-manager "Hand a
required command to an agent with a prompt").

The same documents name the Coffer secrets a skill requires
(``requires: {secrets: [...]}``); :meth:`CliRequirementService.missing_secrets`
answers which of them are not set, asking only whether each name is in the
secret store (never a value). Setting one is the person's task on the Secrets
page, so it carries no hand-off (spec skill-manager "Report a secret a skill
requires that is not set").
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from coffer.application.skill.cli_handoff import cli_handoff
from coffer.domain.skill.cli_declared import DeclaredTool
from coffer.domain.skill.cli_errors import CliNotKnown
from coffer.domain.skill.cli_status import (
    STATUS_ORDER,
    CliStatus,
    LoginState,
    ProbeResult,
    RequiredCommand,
    ServerLauncher,
    SkillRequirements,
    aggregate,
    login_state,
    status_of,
)
from coffer.domain.skill.requirements import requirements_from_skill_md


class CommandProbePort(Protocol):
    """The machine, as far as checking a command goes. Blocking calls."""

    def locate(self, command: str) -> str | None: ...

    def version(self, path: str) -> str | None: ...

    def fingerprint(self, path: str) -> str | None:
        """What identifies this build of the file (its size and mtime), so a
        reinstalled tool is read again; ``None`` when it cannot be read."""
        ...

    def login_ok(self, argv: Sequence[str]) -> bool | None:
        """Exit 0 → ``True``, any other exit → ``False``, could not run or
        timed out → ``None``. The check's output is never returned."""
        ...


@dataclass(frozen=True)
class SkillDocument:
    """A managed skill and its master SKILL.md text (``None`` when unreadable)."""

    uid: str
    name: str
    text: str | None


class SkillDocumentsPort(Protocol):
    async def skill_documents(self) -> Sequence[SkillDocument]: ...


class McpLaunchersPort(Protocol):
    """The enabled stdio MCP servers and the launcher each starts with."""

    async def stdio_launchers(self) -> Sequence[ServerLauncher]: ...


class DeclaredToolsPort(Protocol):
    """The tools the person added by hand (a vault state document)."""

    def all(self) -> list[DeclaredTool]: ...


class CliPathsPort(Protocol):
    """Where this machine found a tool added by an absolute path."""

    def get(self, command: str) -> str | None: ...


@dataclass(frozen=True)
class SkillWarning:
    """A ``requires:`` entry a skill declares that was skipped, and why."""

    skill_uid: str
    skill_name: str
    message: str


@dataclass(frozen=True)
class MissingSecret:
    """A secret a managed skill declares that is not in the secret store."""

    skill_uid: str
    skill_name: str
    secret: str


@dataclass(frozen=True)
class CliView:
    required: RequiredCommand
    probe: ProbeResult
    status: CliStatus
    #: The prompt to hand to an agent; ``None`` for a ready command.
    handoff: str | None = None


@dataclass(frozen=True)
class CliListing:
    items: tuple[CliView, ...]
    warnings: tuple[SkillWarning, ...] = ()


def _now() -> datetime:
    return datetime.now(tz=UTC)


class CliRequirementService:
    def __init__(
        self,
        *,
        skills: SkillDocumentsPort,
        probe: CommandProbePort,
        machine: Callable[[], str],
        servers: McpLaunchersPort | None = None,
        declared: DeclaredToolsPort | None = None,
        paths: CliPathsPort | None = None,
        secret_set: Callable[[str], bool] | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._skills = skills
        #: Whether a secret NAME is in the store; ``None`` when not wired.
        self._secret_set = secret_set
        self._servers = servers
        self._declared = declared
        self._paths = paths
        self._probe = probe
        self._machine = machine
        self._clock = clock
        self._cache: dict[str, ProbeResult] = {}

    # ---------- reads ----------

    async def listing(self) -> CliListing:
        """Every required command, problems first; probes only what has no
        cached result."""
        return await self._listing(force=False)

    async def check_all(self) -> CliListing:
        """Probe every required command again."""
        return await self._listing(force=True)

    async def get(self, command: str) -> CliView:
        return await self._one(command, force=False)

    async def check(self, command: str) -> CliView:
        return await self._one(command, force=True)

    def forget(self, command: str) -> None:
        """Drop the cached probe: the declaration or the tool changed."""
        self._cache.pop(command, None)

    def fingerprint(self, path: str) -> str | None:
        return self._probe.fingerprint(path)

    async def missing_secrets(self) -> tuple[MissingSecret, ...]:
        """Every (skill, secret) whose declared secret is not set, by skill
        then in declared order. Read afresh on each call: a presence check is
        one file lookup, and a secret the person just added must clear."""
        if self._secret_set is None:
            return ()
        is_set = self._secret_set
        out: list[MissingSecret] = []
        for doc in await self._skills.skill_documents():
            if doc.text is None:
                continue
            for name in requirements_from_skill_md(doc.text).secrets:
                if not await asyncio.to_thread(is_set, name):
                    out.append(MissingSecret(doc.uid, doc.name, name))
        return tuple(out)

    # ---------- internals ----------

    async def _required(self) -> tuple[list[RequiredCommand], list[SkillWarning]]:
        parsed: list[SkillRequirements] = []
        warnings: list[SkillWarning] = []
        for doc in await self._skills.skill_documents():
            if doc.text is None:
                continue
            result = requirements_from_skill_md(doc.text)
            parsed.append(SkillRequirements(doc.uid, doc.name, result.requirements))
            warnings.extend(SkillWarning(doc.uid, doc.name, w) for w in result.warnings)
        servers = await self._servers.stdio_launchers() if self._servers else ()
        added = self._declared.all() if self._declared else ()
        return aggregate(parsed, servers, added), warnings

    async def _listing(self, *, force: bool) -> CliListing:
        required, warnings = await self._required()
        await self._probe_rows(required, force=force)
        views = sorted(
            (self._view(row) for row in required),
            key=lambda v: (STATUS_ORDER[v.status], v.required.command),
        )
        return CliListing(tuple(views), tuple(warnings))

    async def _one(self, command: str, *, force: bool) -> CliView:
        required, _warnings = await self._required()
        row = next((r for r in required if r.command == command), None)
        if row is None:
            raise CliNotKnown(command)
        await self._probe_rows([row], force=force)
        return self._view(row)

    async def _probe_rows(self, rows: Sequence[RequiredCommand], *, force: bool) -> None:
        todo = [r for r in rows if force or self._stale(r)]
        if not todo:
            return
        # A login check runs a program with arguments a skill chose, so only an
        # explicit Check runs one — never the read the attention poll makes.
        results = await asyncio.gather(
            *(asyncio.to_thread(self._probe_one, r, run_login=force) for r in todo)
        )
        for row, result in zip(todo, results, strict=True):
            self._cache[row.command] = result

    def _stale(self, row: RequiredCommand) -> bool:
        cached = self._cache.get(row.command)
        return cached is None or cached.login_check != row.login_check

    def _probe_one(self, row: RequiredCommand, *, run_login: bool) -> ProbeResult:
        hint = self._paths.get(row.command) if self._paths else None
        path = self._probe.locate(hint or row.command) or (
            self._probe.locate(row.command) if hint else None
        )
        if path is None:
            return ProbeResult(None, None, None, self._clock(), row.login_check)
        version = self._probe.version(path)
        if row.login_check is None:
            return ProbeResult(path, version, LoginState.NOT_NEEDED, self._clock(), None)
        if not run_login:
            # Declared but not run: not logged out, just not known yet.
            return ProbeResult(path, version, None, self._clock(), row.login_check)
        # The located file runs, not whatever else the name resolves to.
        ok = self._probe.login_ok([path, *row.login_check[1:]])
        login = login_state(row.login_check, ok)
        return ProbeResult(path, version, login, self._clock(), row.login_check)

    def _view(self, row: RequiredCommand) -> CliView:
        probe = self._cache[row.command]
        status = status_of(row, probe)
        return CliView(
            required=row,
            probe=probe,
            status=status,
            handoff=cli_handoff(row, probe, status, self._machine()),
        )


__all__ = [
    "CliListing",
    "CliPathsPort",
    "CliRequirementService",
    "CliView",
    "CommandProbePort",
    "DeclaredToolsPort",
    "McpLaunchersPort",
    "MissingSecret",
    "SkillDocument",
    "SkillDocumentsPort",
    "SkillWarning",
]
