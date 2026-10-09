"""``coffer skill`` — the Skills page: import, delivery, copies and sources.

Spec skill-manager "Manage skills on REST and on the Skills
page". A skill's own files are plain files edited with the reader's own
tools (its master path is in ``coffer skill show``); registering, delivering,
updating from a source and deleting are commands. A skill is named by its name
or its uid. An import is staged first (``stage-*``) and confirmed after.
"""

from __future__ import annotations

from pathlib import Path

import typer

from coffer.surfaces.cli import _io
from coffer.surfaces.cli._options import ExitCode
from coffer.surfaces.cli._route_command import Q, RouteCommand, mount
from coffer.surfaces.cli.groups import group
from coffer.surfaces.cli.registry import maps

S = {"uid": "skill"}
_UI = "Skills · "

SPECS = [
    RouteCommand(
        "skill list",
        "GET",
        "/skills",
        _UI + "list",
        "Every skill with its delivery and source state.",
        columns=("name", "enabled", "source", "uid"),
    ),
    RouteCommand(
        "skill show",
        "GET",
        "/skills/{uid}",
        _UI + "open a skill",
        "One skill: its master path, requirements, delivery and source.",
        names=S,
    ),
    RouteCommand(
        "skill files",
        "GET",
        "/skills/{uid}/files",
        _UI + "Files tab",
        "The skill's files and its master path (edit them with your own tools).",
        names=S,
    ),
    RouteCommand(
        "skill delete",
        "DELETE",
        "/skills/{uid}",
        _UI + "Delete",
        "Delete a skill and its copies in agents.",
        names=S,
        query=(Q("keep_foreign_copies", "Keep copies Coffer did not write", flag=True),),
    ),
    RouteCommand(
        "skill delete-many",
        "POST",
        "/skills/bulk-delete",
        _UI + "Delete selected",
        "Delete several skills. Body: uids, keep_foreign_copies.",
        body=True,
    ),
    RouteCommand(
        "skill verify",
        "POST",
        "/skills/verify",
        _UI + "Verify",
        "Check every skill's delivery to the agents it reaches.",
    ),
    RouteCommand(
        "skill repair",
        "POST",
        "/skills/repair",
        _UI + "Repair",
        "Rewrite every delivery that drifted.",
    ),
    RouteCommand(
        "skill conformance-handoff",
        "POST",
        "/skills/conformance/handoff",
        _UI + "Ask an agent to fix the format",
        "The prompt that hands fixing skills' format to an agent. Body: uids.",
        body=True,
    ),
    RouteCommand(
        "skill copy compare",
        "GET",
        "/skills/{uid}/copies/{agent_uid}",
        _UI + "a copy that differs · compare",
        "How an agent's copy differs from the master.",
        names=S,
    ),
    RouteCommand(
        "skill copy resolve",
        "POST",
        "/skills/{uid}/copies/{agent_uid}/resolve",
        _UI + "a copy that differs · keep one",
        "Keep the master or the agent's copy. Body: keep (master | copy).",
        names=S,
        body=True,
    ),
    RouteCommand(
        "skill orphan list",
        "GET",
        "/skills/orphans",
        _UI + "folders no skill owns",
        "Folders in the skills store that no skill owns.",
    ),
    RouteCommand(
        "skill orphan files",
        "GET",
        "/skills/orphans/{name}/files",
        _UI + "an orphan's files",
        "An orphan folder's files.",
    ),
    RouteCommand(
        "skill orphan adopt",
        "POST",
        "/skills/orphans/{name}/adopt",
        _UI + "an orphan · Adopt",
        "Register an orphan folder as a skill.",
    ),
    RouteCommand(
        "skill orphan remove",
        "DELETE",
        "/skills/orphans/{name}",
        _UI + "an orphan · Remove",
        "Delete an orphan folder.",
    ),
    RouteCommand(
        "skill stage-folder",
        "POST",
        "/skills/stage/folder",
        _UI + "Import · a folder",
        "Stage skills from a folder on this machine. Body: path.",
        body=True,
    ),
    RouteCommand(
        "skill stage-git",
        "POST",
        "/skills/stage/git",
        _UI + "Import · a git repository",
        "Stage skills from a git repository. Body: url, ref, path.",
        body=True,
    ),
    RouteCommand(
        "skill stage-confirm",
        "POST",
        "/skills/stage/{staging_id}/confirm",
        _UI + "Import · Import",
        "Import staged skills. Body: skills, replace.",
        body=True,
    ),
    RouteCommand(
        "skill stage-cancel",
        "DELETE",
        "/skills/stage/{staging_id}",
        _UI + "Import · Cancel",
        "Drop a staged import.",
    ),
    RouteCommand(
        "skill source check",
        "POST",
        "/skills/{uid}/source/check",
        _UI + "Source · Check for updates",
        "Ask the skill's source for a newer version.",
        names=S,
    ),
    RouteCommand(
        "skill source change",
        "POST",
        "/skills/{uid}/source/change",
        _UI + "Source · Change source · preview",
        "Stage the skill from another source. Body: url, ref, path.",
        names=S,
        body=True,
    ),
    RouteCommand(
        "skill source change-apply",
        "POST",
        "/skills/{uid}/source/change/apply",
        _UI + "Source · Change source · apply",
        "Apply a staged change of source. Body: staging_id.",
        names=S,
        body=True,
    ),
    RouteCommand(
        "skill source handoff",
        "POST",
        "/skills/{uid}/source/handoff",
        _UI + "Source · Ask an agent to merge",
        "The prompt that hands merging an upstream update to an agent.",
        names=S,
    ),
    RouteCommand(
        "skill source merged",
        "POST",
        "/skills/{uid}/source/merged",
        _UI + "Source · record the merge",
        "Record that the upstream update was merged. Body: commit.",
        names=S,
        body=True,
    ),
    RouteCommand(
        "skill update-check show",
        "GET",
        "/skills/update-check",
        "Settings · Skills · update check",
        "How often skills' sources are checked.",
    ),
    RouteCommand(
        "skill update-check set",
        "PUT",
        "/skills/update-check",
        "Settings · Skills · update check",
        "Set how often skills' sources are checked. Body: interval.",
        body=True,
    ),
]

mount(SPECS)

skills = group("skill")


@skills.command("stage-archive")
@maps("skill stage-archive", ("POST", "/skills/stage/archive"), ui=_UI + "Import · an archive")
def stage_archive(
    archive: Path = typer.Argument(..., help="A .zip or .skill archive of one or more skills"),
    as_json: bool = _io.json_option(),
) -> None:
    """Stage skills from an archive file; confirm with ``skill stage-confirm``."""
    try:
        data = archive.expanduser().read_bytes()
    except OSError as e:
        _io.fail(
            "CLI_INVALID_INPUT",
            f"cannot read {archive}: {e}",
            ExitCode.INVALID_INPUT,
            as_json=as_json,
        )
    staged = _io.call(
        "POST", "/skills/stage/archive", as_json=as_json, files={"file": (archive.name, data)}
    )
    _io.emit(staged, as_json=as_json)
