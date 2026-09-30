"""Wire shapes of ``/api/v1/clis`` (spec skill-manager "Cover required
commands on REST, the command line and the web")."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from coffer.application.skill.cli_install import InstallSnapshot
from coffer.application.skill.cli_requirements import CliListing, CliView, SkillWarning
from coffer.domain.skill.cli_status import CliStatus

CliStatusOut = Literal["missing", "outdated", "logged_out", "ready"]
CliLoginStateOut = Literal["logged_in", "logged_out", "not_needed"]
CliInstallStateOut = Literal["running", "succeeded", "failed"]


class CliNeededByOut(BaseModel):
    """One skill that requires the command, with what it asked for."""

    skill_uid: str
    skill_name: str
    min_version: str | None
    why: str | None


class CliLoginOut(BaseModel):
    """``state`` is ``None`` when the command was not found, so its login check
    could not run. ``command`` is the login command to copy — Coffer never
    runs it. ``check`` is the declared login check."""

    state: CliLoginStateOut | None
    check: list[str] | None
    command: str | None


class CliOut(BaseModel):
    command: str
    title: str | None
    status: CliStatusOut
    #: Where the agent's ``PATH`` finds it; ``None`` when missing.
    path: str | None
    #: What ``--version`` printed; ``None`` when missing or unreadable.
    version: str | None
    #: The highest minimum any skill asks for.
    min_version: str | None
    login: CliLoginOut
    #: The Homebrew formula the skills declare.
    brew: str | None
    #: The Homebrew command an install would run now (``brew install jq``);
    #: ``None`` when there is nothing to install or no formula.
    install_command: str | None
    #: The latest install job's state, when one ran since the daemon started.
    install_state: CliInstallStateOut | None
    needed_by: list[CliNeededByOut]
    checked_at: datetime


class CliWarningOut(BaseModel):
    """A ``requires:`` entry a skill declares that was skipped, and why."""

    skill_uid: str
    skill_name: str
    message: str


class CliListOut(BaseModel):
    items: list[CliOut]
    warnings: list[CliWarningOut]


class CliInstallIn(BaseModel):
    """The formula the confirmation showed; it must equal the declared one."""

    formula: str = Field(min_length=1, max_length=128)


class CliInstallOut(BaseModel):
    command: str
    formula: str
    action: Literal["install", "upgrade"]
    #: The exact argv run: the located ``brew``, the action, the formula.
    argv: list[str]
    state: CliInstallStateOut
    exit_code: int | None
    started_at: datetime
    finished_at: datetime | None
    #: The number of ``lines[0]``; ``next_line`` is the ``since`` to poll with.
    first_line: int
    lines: list[str]
    next_line: int


def cli_out(view: CliView) -> CliOut:
    row, probe = view.required, view.probe
    install_command: str | None = None
    if row.brew is not None and view.status in (CliStatus.MISSING, CliStatus.OUTDATED):
        verb = "install" if view.status is CliStatus.MISSING else "upgrade"
        install_command = f"brew {verb} {row.brew}"
    return CliOut(
        command=row.command,
        title=row.title,
        status=view.status.value,
        path=probe.path,
        version=probe.version,
        min_version=row.min_version,
        login=CliLoginOut(
            state=probe.login.value if probe.login is not None else None,
            check=list(row.login_check) if row.login_check is not None else None,
            command=row.login,
        ),
        brew=row.brew,
        install_command=install_command,
        install_state=view.install_state,  # type: ignore[arg-type]
        needed_by=[
            CliNeededByOut(
                skill_uid=n.skill_uid,
                skill_name=n.skill_name,
                min_version=n.min_version,
                why=n.why,
            )
            for n in row.needed_by
        ],
        checked_at=probe.checked_at,
    )


def _warning_out(w: SkillWarning) -> CliWarningOut:
    return CliWarningOut(skill_uid=w.skill_uid, skill_name=w.skill_name, message=w.message)


def cli_list_out(listing: CliListing) -> CliListOut:
    return CliListOut(
        items=[cli_out(v) for v in listing.items],
        warnings=[_warning_out(w) for w in listing.warnings],
    )


def cli_install_out(job: InstallSnapshot) -> CliInstallOut:
    return CliInstallOut(
        command=job.command,
        formula=job.formula,
        action=job.action,  # type: ignore[arg-type]
        argv=list(job.argv),
        state=job.state.value,
        exit_code=job.exit_code,
        started_at=job.started_at,
        finished_at=job.finished_at,
        first_line=job.first_line,
        lines=list(job.lines),
        next_line=job.next_line,
    )
