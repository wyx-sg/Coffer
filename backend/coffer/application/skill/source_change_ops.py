"""Change a Git-imported skill's source (spec skill-manager "Change a
Git-imported skill's source").

Stages the new repository, ref and folder the way an import from Git does,
requires one valid skill there with this skill's fixed name, and answers the
commit and the names of the files that would be added, removed or changed
against the folder as it is now — names only, no diff. Nothing is replaced
until the stage is applied (:func:`apply_change`), which swaps the folder in
atomically through the path an overwriting import takes, so the reach and the
delivered links stay, and records the new source pinned to the new commit;
cancelling the stage leaves the skill and its source exactly as they were.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.skill.lifecycle_ops import register_from_validated
from coffer.application.skill.staging import SourceChangeStage, remove_dir
from coffer.application.skill.update_ops import git_source_of
from coffer.domain.audit import AuditEventType
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


@dataclass(frozen=True)
class FileName:
    path: str
    status: str  # "added" | "removed" | "modified"


@dataclass(frozen=True)
class SourceChangePreview:
    stage_id: str
    commit: str
    files: list[FileName]


async def preview_change(
    svc: SkillSourceService, skill: Resource, url: str, ref: str | None, path: str | None
) -> SourceChangePreview:
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
        files = [
            FileName(c.path, c.status)
            for c in diff_folders(master, incoming)
            if c.path != ".coffer.meta.json"
        ]
    except BaseException:
        remove_dir(stage_dir)
        raise
    svc.staging.put(
        SourceChangeStage(
            id=stage_id,
            skill_uid=skill.uid,
            dir=stage_dir,
            from_commit=current.commit,
            to_commit=commit,
            incoming=incoming,
            new_source=GitImportSource(
                url=loc.url,
                ref=loc.ref,
                subpath=loc.subpath,
                commit=commit,
                content_hash=content_hash,
            ),
        )
    )
    return SourceChangePreview(stage_id=stage_id, commit=commit, files=files)


async def apply_change(
    svc: SkillSourceService, skill: Resource, stage_id: str, *, actor: str
) -> Resource:
    """Swap the staged source's folder in, keep reach and links, pin the new commit."""
    stage = svc.staging.get(stage_id)
    if not isinstance(stage, SourceChangeStage):
        raise SkillValidationError("not_a_source_change_stage", {"path": stage_id})
    if stage.skill_uid != skill.uid:
        raise SkillValidationError("stage_for_another_skill", {"path": stage_id})
    result = validate_skill_folder(stage.incoming, size_limit_bytes=svc.size_limit)
    if isinstance(result, ValidationFailure):
        raise SkillValidationError(result.reason, result.details)
    try:
        updated = await register_from_validated(
            service=svc.skills,
            src=stage.incoming,
            validation=result,
            source_meta=stage.new_source,
            event=AuditEventType.SKILL_UPDATED,
            actor=actor,
            overwrite=True,
            audit_details={"from_commit": stage.from_commit, "to_commit": stage.to_commit},
        )
    finally:
        svc.staging.discard(stage.id)
    status = await svc.status_repo.get(updated.uid)
    if status is not None:
        await svc.status_repo.put(
            status.with_(
                latest_commit=stage.to_commit,
                commits_ahead=0,
                files_changed=0,
                commits=(),
                error=None,
            )
        )
    return updated


__all__ = ["FileName", "SourceChangePreview", "apply_change", "preview_change"]
