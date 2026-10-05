"""Wire shapes of ``/api/v1/clis``.

Spec skill-manager "Serve required commands on REST and the web" and
"Declare a command-line tool without a skill".
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from coffer.application.skill.cli_requirements import CliListing, CliView, SkillWarning
from coffer.application.skill.cli_tools import CliPreview
from coffer.surfaces.http.handoff_schemas import HandoffOut, handoff_out

CliStatusOut = Literal["missing", "outdated", "logged_out", "ready"]
CliLoginStateOut = Literal["logged_in", "logged_out", "not_needed"]
CliCofferUseOut = Literal["vault_history", "sync"]


class CliNeededByOut(BaseModel):
    """One skill that requires the command, with what it asked for."""

    skill_uid: str
    skill_name: str
    min_version: str | None
    why: str | None


class CliServerOut(BaseModel):
    """One enabled stdio MCP server started with the command (or with a
    launcher it provides: ``uvx`` for ``uv``, ``npx`` for ``node``)."""

    server_uid: str
    server_name: str
    #: The launcher its config names, e.g. ``uvx``.
    launcher: str


class CliLoginOut(BaseModel):
    """``state`` is ``None`` when the command was not found, so its login check
    could not run, or when the check has not been run yet (only a Check runs
    it). ``command`` is the login command to copy — Coffer never runs it.
    ``check`` is the declared login check."""

    state: CliLoginStateOut | None
    check: list[str] | None
    command: str | None


class CliOut(BaseModel):
    command: str
    title: str | None
    #: What the person wrote about it — when they added it by hand, or on its
    #: page for a tool a skill or MCP server requires.
    description: str | None
    #: The person added this tool by hand (alone or besides a skill that
    #: requires it); ``needed_by`` and ``needed_by_servers`` may both be empty.
    added: bool
    status: CliStatusOut
    #: Where the agent's ``PATH`` finds it; ``None`` when missing.
    path: str | None
    #: What ``--version`` printed; ``None`` when missing or unreadable.
    version: str | None
    #: The highest minimum any skill or the hand-added declaration asks for
    #: (MCP servers ask for none).
    min_version: str | None
    login: CliLoginOut
    #: The prompt to hand to an agent: install a missing command, update an
    #: outdated one, or help the person log in. ``None`` when ready.
    handoff: HandoffOut | None
    #: The skills that declare the command.
    needed_by: list[CliNeededByOut]
    #: The MCP servers that start with it.
    needed_by_servers: list[CliServerOut]
    #: What Coffer itself runs it for (``git``: the vault's history and
    #: sync); empty when Coffer does not run it.
    needed_by_coffer: list[CliCofferUseOut]
    checked_at: datetime


class CliWarningOut(BaseModel):
    """A ``requires:`` entry a skill declares that was skipped, and why."""

    skill_uid: str
    skill_name: str
    message: str


class CliListOut(BaseModel):
    items: list[CliOut]
    warnings: list[CliWarningOut]


class CliAddIn(BaseModel):
    """Declare a tool by hand. ``command`` is a command name (``jq``) or the
    absolute path of an executable (``/opt/tools/bin/jq``; the file name is
    the command). ``login_check`` is a command line that starts with the tool,
    like ``gh auth status``."""

    command: str = Field(min_length=1, max_length=512)
    title: str | None = None
    description: str | None = None
    min_version: str | None = None
    login_check: str | None = None


class CliEditIn(BaseModel):
    """Change a hand-added tool; a field left out stays, ``null`` clears it.
    A tool a skill or MCP server requires takes only ``description``."""

    title: str | None = None
    description: str | None = None
    min_version: str | None = None
    login_check: str | None = None


class CliPreviewIn(BaseModel):
    command: str = Field(min_length=1, max_length=512)


class CliPreviewOut(BaseModel):
    """What Coffer found for a name or path, before anything is saved."""

    command: str
    #: Where it was found; ``None`` when it is not on this machine.
    path: str | None
    version: str | None
    #: Already added by hand.
    added: bool
    #: A skill or MCP server already requires it.
    required: bool


def cli_preview_out(p: CliPreview) -> CliPreviewOut:
    return CliPreviewOut(
        command=p.command, path=p.path, version=p.version, added=p.added, required=p.required
    )


def cli_out(view: CliView) -> CliOut:
    row, probe = view.required, view.probe
    return CliOut(
        command=row.command,
        title=row.title,
        description=row.description,
        added=row.added,
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
        needed_by_servers=[
            CliServerOut(server_uid=s.server_uid, server_name=s.server_name, launcher=s.launcher)
            for s in row.needed_by_servers
        ],
        needed_by_coffer=[u.value for u in row.needed_by_coffer],
        checked_at=probe.checked_at,
    )


def _warning_out(w: SkillWarning) -> CliWarningOut:
    return CliWarningOut(skill_uid=w.skill_uid, skill_name=w.skill_name, message=w.message)


def cli_list_out(listing: CliListing) -> CliListOut:
    return CliListOut(
        items=[cli_out(v) for v in listing.items],
        warnings=[_warning_out(w) for w in listing.warnings],
    )
