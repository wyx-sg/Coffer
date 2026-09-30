"""Wire shapes of ``/api/v1/clis`` (spec skill-manager "Serve required
commands on REST, the command line and the web")."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from coffer.application.skill.cli_requirements import CliListing, CliView, SkillWarning
from coffer.surfaces.http.handoff_schemas import HandoffOut, handoff_out

CliStatusOut = Literal["missing", "outdated", "logged_out", "ready"]
CliLoginStateOut = Literal["logged_in", "logged_out", "not_needed"]


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
    #: The prompt to hand to an agent: install a missing command, update an
    #: outdated one, or help the person log in. ``None`` when ready.
    handoff: HandoffOut | None
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


def cli_out(view: CliView) -> CliOut:
    row, probe = view.required, view.probe
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
        handoff=handoff_out(view.handoff),
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
