"""The command-line tools managed skills require: read, checked, installed.

``CliRequirementService`` reads every managed skill's master SKILL.md at check
time (so an edit made in the user's editor is picked up by the next read),
aggregates one row per command (``domain/skill/cli_status.py``), and probes
each command through a :class:`CommandProbePort` in a worker thread. Results
are cached per command until the user asks to check again, an install of it
finishes, or the daemon restarts; a command no result is cached for is probed
on the read that first needs it.

Installing is Homebrew only, through an :class:`InstallerPort`, one job per
command, audited at its start and end (spec skill-manager "Install a required
command only through Homebrew and only when asked").
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.application.skill.cli_install import InstallJob, InstallSnapshot
from coffer.domain.audit import AuditEventType
from coffer.domain.skill.cli_errors import (
    CliFormulaMismatch,
    CliInstallNotFound,
    CliInstallRunning,
    CliNotInstallable,
    CliNotRequired,
    HomebrewNotFound,
)
from coffer.domain.skill.cli_status import (
    STATUS_ORDER,
    CliStatus,
    ProbeResult,
    RequiredCommand,
    SkillRequirements,
    aggregate,
    login_state,
    status_of,
)
from coffer.domain.skill.requirements import requirements_from_skill_md

_log = logging.getLogger(__name__)


class CommandProbePort(Protocol):
    """The machine, as far as checking a command goes. Blocking calls."""

    def locate(self, command: str) -> str | None: ...

    def version(self, path: str) -> str | None: ...

    def login_ok(self, argv: Sequence[str]) -> bool | None:
        """Exit 0 → ``True``, any other exit → ``False``, could not run or
        timed out → ``None``. The check's output is never returned."""
        ...


class InstallerPort(Protocol):
    """Homebrew. Blocking calls."""

    def locate(self) -> str | None: ...

    def run(self, argv: Sequence[str], on_line: Callable[[str], None]) -> int: ...


@dataclass(frozen=True)
class SkillDocument:
    """A managed skill and its master SKILL.md text (``None`` when unreadable)."""

    uid: str
    name: str
    text: str | None


class SkillDocumentsPort(Protocol):
    async def skill_documents(self) -> Sequence[SkillDocument]: ...


@dataclass(frozen=True)
class SkillWarning:
    """A ``requires:`` entry a skill declares that was skipped, and why."""

    skill_uid: str
    skill_name: str
    message: str


@dataclass(frozen=True)
class CliView:
    required: RequiredCommand
    probe: ProbeResult
    status: CliStatus
    #: The latest install job's state for this command, if one ran.
    install_state: str | None = None


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
        installer: InstallerPort,
        audit: AuditService,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._skills = skills
        self._probe = probe
        self._installer = installer
        self._audit = audit
        self._clock = clock
        self._cache: dict[str, ProbeResult] = {}
        self._jobs: dict[str, InstallJob] = {}
        self._tasks: set[asyncio.Task[None]] = set()

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

    def install_status(self, command: str, since: int = 0) -> InstallSnapshot:
        job = self._jobs.get(command)
        if job is None:
            raise CliInstallNotFound(command)
        return job.snapshot(since)

    # ---------- install ----------

    async def start_install(self, command: str, formula: str, *, actor: str) -> InstallSnapshot:
        """Start ``brew install|upgrade <formula>`` for a missing or outdated
        command whose declared formula is ``formula``. Refused — and nothing
        runs — otherwise."""
        view = await self.get(command)
        declared = view.required.brew
        if declared is None:
            raise CliNotInstallable(command, "no_formula")
        if view.status not in (CliStatus.MISSING, CliStatus.OUTDATED):
            raise CliNotInstallable(command, "not_needed")
        if formula != declared:
            raise CliFormulaMismatch(command, declared, formula)
        brew = await asyncio.to_thread(self._installer.locate)
        if brew is None:
            raise HomebrewNotFound()
        current = self._jobs.get(command)
        if current is not None and current.running:
            raise CliInstallRunning(command)
        action = "install" if view.status is CliStatus.MISSING else "upgrade"
        job = InstallJob(
            command=command,
            formula=declared,
            action=action,
            argv=(brew, action, declared),
            started_at=self._clock(),
        )
        self._jobs[command] = job
        await self._audit.record(
            AuditEventType.CLI_INSTALL_STARTED,
            actor=actor,
            details={"command": command, "formula": declared, "argv": list(job.argv)},
        )
        task = asyncio.create_task(self._run(job, actor))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job.snapshot()

    async def wait_for_installs(self) -> None:
        """Wait for every running install (shutdown, tests)."""
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def _run(self, job: InstallJob, actor: str) -> None:
        code: int | None
        try:
            code = await asyncio.to_thread(self._installer.run, job.argv, job.append)
        except Exception as exc:
            job.append(f"coffer: could not run {job.argv[0]}: {exc}")
            code = None
        # Probed again before the job reads as finished, so a caller that saw
        # it end reads the command's new state.
        try:
            await self._one(job.command, force=True)
        except Exception:
            _log.warning("skill.cli.reprobe_failed command=%s", job.command, exc_info=True)
        try:
            await self._audit.record(
                AuditEventType.CLI_INSTALL_FINISHED,
                actor=actor,
                details={
                    "command": job.command,
                    "formula": job.formula,
                    "argv": list(job.argv),
                    "exit_code": code,
                    "output_tail": job.tail(),
                },
            )
        finally:
            job.finish(code, self._clock())

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
        return aggregate(parsed), warnings

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
            raise CliNotRequired(command)
        await self._probe_rows([row], force=force)
        return self._view(row)

    async def _probe_rows(self, rows: Sequence[RequiredCommand], *, force: bool) -> None:
        todo = [r for r in rows if force or self._stale(r)]
        if not todo:
            return
        results = await asyncio.gather(*(asyncio.to_thread(self._probe_one, r) for r in todo))
        for row, result in zip(todo, results, strict=True):
            self._cache[row.command] = result

    def _stale(self, row: RequiredCommand) -> bool:
        cached = self._cache.get(row.command)
        return cached is None or cached.login_check != row.login_check

    def _probe_one(self, row: RequiredCommand) -> ProbeResult:
        path = self._probe.locate(row.command)
        if path is None:
            return ProbeResult(None, None, None, self._clock(), row.login_check)
        version = self._probe.version(path)
        ok: bool | None = None
        if row.login_check is not None:
            # The located file runs, not whatever else the name resolves to.
            ok = self._probe.login_ok([path, *row.login_check[1:]])
        login = login_state(row.login_check, ok)
        return ProbeResult(path, version, login, self._clock(), row.login_check)

    def _view(self, row: RequiredCommand) -> CliView:
        probe = self._cache[row.command]
        job = self._jobs.get(row.command)
        return CliView(
            required=row,
            probe=probe,
            status=status_of(row, probe),
            install_state=job.state.value if job is not None else None,
        )


__all__ = [
    "CliListing",
    "CliRequirementService",
    "CliView",
    "CommandProbePort",
    "InstallerPort",
    "SkillDocument",
    "SkillDocumentsPort",
    "SkillWarning",
]
