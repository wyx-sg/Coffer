"""Change a Git-imported skill's source (spec skill-manager "Change a
Git-imported skill's source").

Stages the new repository, ref and folder the way an import from Git does,
requires one valid skill there with this skill's fixed name, and answers the
same preview an update does — its changes measured against the folder as it
is now, local edits included. Nothing is replaced until the preview is
applied (``update_ops.apply``), which then records the new source; cancelling
the stage leaves the skill and its source exactly as they were.
"""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

from coffer.application.skill.staging import UpdateStage, remove_dir
from coffer.application.skill.update_ops import UpdatePreview, git_source_of
from coffer.domain.errors import SkillValidationError
from coffer.domain.resource import Resource
from coffer.domain.skill.content_hash import folder_content_hash
from coffer.domain.skill.folder_diff import diff_folders
from coffer.domain.skill.git_url import parse_git_location
from coffer.domain.skill.source import GitImportSource
from coffer.domain.skill.validator import ValidationFailure, validate_skill_folder
from coffer.domain.skill_source_errors import SkillSourceRejected

if TYPE_CHECKING:
    from coffer.application.skill.source_service import SkillSourceService


async def preview_change(
    svc: SkillSourceService, skill: Resource, url: str, ref: str | None, path: str | None
) -> UpdatePreview:
    current = git_source_of(skill)  # refuses a skill that did not come from Git
    try:
        loc = parse_git_location(url, ref, path)
    except ValueError as exc:
        raise SkillValidationError("git_location_invalid", {"path": str(exc)}) from exc
    stage_id, stage_dir = svc.staging.new_dir()
    try:
        repo = stage_dir / "repo"
        await svc.git.clone(loc.url, repo)
        commit = await svc.git.resolve(repo, loc.ref, url=loc.url)
        incoming = await svc.git.checkout(
            repo, commit, loc.subpath, stage_dir / "incoming", url=loc.url
        )
        result = validate_skill_folder(incoming, size_limit_bytes=svc.size_limit)
        if isinstance(result, ValidationFailure):
            raise SkillValidationError(result.reason, result.details)
        if result.frontmatter.name != skill.name:
            raise SkillSourceRejected(
                "source_renames_skill",
                f"the new source's SKILL.md names {result.frontmatter.name!r}, not "
                f"{skill.name!r}; a skill's name is fixed, so it cannot come from there",
                {"name": result.frontmatter.name},
            )
        master = pathlib.Path(svc.skills._store.paths_for(skill.name).folder)
        content_hash = folder_content_hash(incoming)
        view = UpdatePreview(
            stage_id=stage_id,
            skill_uid=skill.uid,
            from_commit=current.commit,
            to_commit=commit,
            commits=[],
            changes=[c for c in diff_folders(master, incoming) if c.path != ".coffer.meta.json"],
            conflict=False,
            local_changes=[],
        )
    except BaseException:
        remove_dir(stage_dir)
        raise
    svc.staging.put(
        UpdateStage(
            id=stage_id,
            skill_uid=skill.uid,
            dir=stage_dir,
            from_commit=current.commit,
            to_commit=commit,
            pinned=None,
            incoming=incoming,
            content_hash=content_hash,
            preview=view,
            new_source=GitImportSource(
                url=loc.url,
                ref=loc.ref,
                subpath=loc.subpath,
                commit=commit,
                content_hash=content_hash,
            ),
        )
    )
    return view


__all__ = ["preview_change"]
