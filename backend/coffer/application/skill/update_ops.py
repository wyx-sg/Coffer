"""Check, preview and apply a Git-imported skill's upstream updates.

Spec skill-manager "Update a Git-imported skill from its source". A check
fetches into a staging directory it removes again and records what it found in
``skill_source_status``; a preview checks the pinned and the new folder out
side by side into a stage the dialog keeps until it applies or closes; applying
swaps the new folder in through the same path an overwriting import takes, so
the name, the bindings and the delivered links stay where they are.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from coffer.application.skill.lifecycle_ops import register_from_validated
from coffer.application.skill.staging import UpdateStage, remove_dir
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SkillValidationError
from coffer.domain.resource import Resource
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.content_hash import folder_content_hash
from coffer.domain.skill.folder_diff import FileChange, TextVersion, diff_folders, read_text
from coffer.domain.skill.source import GitImportSource
from coffer.domain.skill.source_status import SourceStatus
from coffer.domain.skill.validator import ValidationFailure, validate_skill_folder
from coffer.domain.skill_source_errors import (
    SkillNotFromGit,
    SkillSourceRejected,
    SkillSourceUnreachable,
    SkillUpdateConflict,
)

if TYPE_CHECKING:
    from coffer.application.skill.source_service import SkillSourceService

#: How often the worker looks, and how stale a check must be to be redone.
CHECK_INTERVAL = timedelta(hours=6)


@dataclass(frozen=True)
class CommitLine:
    id: str
    subject: str


@dataclass(frozen=True)
class UpdatePreview:
    stage_id: str
    skill_uid: str
    from_commit: str
    to_commit: str
    commits: list[CommitLine]
    changes: list[FileChange]
    #: The master folder no longer matches the pinned commit's content.
    conflict: bool
    local_changes: list[FileChange]


@dataclass(frozen=True)
class CompareView:
    path: str
    local: TextVersion
    pinned: TextVersion
    incoming: TextVersion


def git_source_of(skill: Resource) -> GitImportSource:
    source = SkillConfig.model_validate(skill.config).source
    if not isinstance(source, GitImportSource):
        raise SkillNotFromGit(skill.name)
    return source


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _status(svc: SkillSourceService, skill: Resource) -> SourceStatus:
    return await svc.status_repo.get(skill.uid) or SourceStatus(skill_uid=skill.uid)


def _edited(svc: SkillSourceService, skill: Resource, source: GitImportSource) -> bool:
    master = pathlib.Path(svc.skills._store.paths_for(skill.name).folder)
    return not master.is_dir() or folder_content_hash(master) != source.content_hash


async def check(svc: SkillSourceService, skill: Resource) -> SourceStatus:
    """Fetch the skill's repository into staging and record what the ref holds now.

    Never raises for git failing: an unreachable source is a state the skill
    reports (git's message, the last success kept), not an error of the check.
    """
    source = git_source_of(skill)
    status = await _status(svc, skill)
    now = _now()
    stage_id, stage_dir = svc.staging.new_dir()
    try:
        repo = stage_dir / "repo"
        await svc.git.clone(source.url, repo)
        latest = await svc.git.resolve(repo, source.ref, url=source.url)
        if latest == source.commit:
            commits, files = 0, 0
        else:
            found = await svc.git.commits(repo, source.commit, latest, source.subpath)
            commits = len(found)
            files = (
                len(await svc.git.changed_files(repo, source.commit, latest, source.subpath))
                if await svc.git.has_commit(repo, source.commit)
                else 0
            )
        status = status.with_(
            checked_at=now,
            last_success_at=now,
            error=None,
            latest_commit=latest,
            commits_ahead=commits,
            files_changed=files,
        )
    except SkillSourceUnreachable as exc:
        status = status.with_(checked_at=now, error=exc.git_message)
    finally:
        remove_dir(stage_dir)
        svc.staging.discard(stage_id)
    return await svc.status_repo.put(status)


async def check_due(svc: SkillSourceService, *, now: datetime | None = None) -> int:
    """Check every Git-imported skill not checked within the interval; the count checked."""
    now = now or _now()
    statuses = await svc.status_repo.list_all()
    done = 0
    for skill in await svc.skills._rs.list(kind="skill"):
        try:
            git_source_of(skill)
        except SkillNotFromGit:
            continue
        last = statuses.get(skill.uid)
        if (
            last is not None
            and last.checked_at is not None
            and now - last.checked_at < CHECK_INTERVAL
        ):
            continue
        await check(svc, skill)
        done += 1
    return done


async def preview(svc: SkillSourceService, skill: Resource) -> UpdatePreview:
    """Stage the pinned and the new folder side by side and say what would change."""
    source = git_source_of(skill)
    stage_id, stage_dir = svc.staging.new_dir()
    try:
        repo = stage_dir / "repo"
        await svc.git.clone(source.url, repo)
        latest = await svc.git.resolve(repo, source.ref, url=source.url)
        incoming = await svc.git.checkout(
            repo, latest, source.subpath, stage_dir / "incoming", url=source.url
        )
        pinned: pathlib.Path | None = None
        commits: list[CommitLine] = []
        if await svc.git.has_commit(repo, source.commit):
            pinned = await svc.git.checkout(
                repo, source.commit, source.subpath, stage_dir / "pinned", url=source.url
            )
            if latest != source.commit:
                commits = [
                    CommitLine(c.id, c.subject)
                    for c in await svc.git.commits(repo, source.commit, latest, source.subpath)
                ]
        result = validate_skill_folder(incoming, size_limit_bytes=svc.size_limit)
        if isinstance(result, ValidationFailure):
            raise SkillValidationError(result.reason, result.details)
        if result.frontmatter.name != skill.name:
            raise SkillSourceRejected(
                "update_renames_skill",
                f"the update's SKILL.md names {result.frontmatter.name!r}, not {skill.name!r}; "
                "a skill's name is fixed, so this update cannot be taken",
                {"name": result.frontmatter.name},
            )
        master = pathlib.Path(svc.skills._store.paths_for(skill.name).folder)
        conflict = _edited(svc, skill, source)
        local = diff_folders(pinned, master) if conflict else []
        view = UpdatePreview(
            stage_id=stage_id,
            skill_uid=skill.uid,
            from_commit=source.commit,
            to_commit=latest,
            commits=commits,
            changes=diff_folders(pinned, incoming),
            conflict=conflict,
            local_changes=local,
        )
    except BaseException:
        remove_dir(stage_dir)
        raise
    svc.staging.put(
        UpdateStage(
            id=stage_id,
            skill_uid=skill.uid,
            dir=stage_dir,
            from_commit=source.commit,
            to_commit=latest,
            pinned=pinned,
            incoming=incoming,
            content_hash=folder_content_hash(incoming),
            preview=view,
        )
    )
    return view


def _update_stage(svc: SkillSourceService, stage_id: str) -> UpdateStage:
    stage = svc.staging.get(stage_id)
    if not isinstance(stage, UpdateStage):
        raise SkillValidationError("not_an_update_stage", {"path": stage_id})
    return stage


def compare(svc: SkillSourceService, skill: Resource, stage_id: str, path: str) -> CompareView:
    """One file as the master, the pinned commit and the new commit hold it."""
    stage = _update_stage(svc, stage_id)
    parts = [p for p in path.replace("\\", "/").split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts) or path.startswith("/"):
        raise SkillValidationError("path_outside_skill", {"path": path})
    rel = "/".join(parts)
    master = pathlib.Path(svc.skills._store.paths_for(skill.name).folder)
    return CompareView(
        path=rel,
        local=read_text(master / rel),
        pinned=read_text(stage.pinned / rel if stage.pinned else None),
        incoming=read_text(stage.incoming / rel),
    )


async def apply(
    svc: SkillSourceService,
    skill: Resource,
    stage_id: str,
    *,
    discard_local_edits: bool,
    actor: str,
) -> Resource:
    """Swap the new commit's folder in, move the pin, keep reach and links."""
    stage = _update_stage(svc, stage_id)
    if stage.skill_uid != skill.uid:
        raise SkillValidationError("stage_for_another_skill", {"path": stage_id})
    source = git_source_of(skill)
    if _edited(svc, skill, source) and not discard_local_edits:
        raise SkillUpdateConflict(skill.name)
    result = validate_skill_folder(stage.incoming, size_limit_bytes=svc.size_limit)
    if isinstance(result, ValidationFailure):
        raise SkillValidationError(result.reason, result.details)
    try:
        updated = await register_from_validated(
            service=svc.skills,
            src=stage.incoming,
            validation=result,
            source_meta=source.model_copy(
                update={"commit": stage.to_commit, "content_hash": stage.content_hash}
            ),
            event=AuditEventType.SKILL_UPDATED,
            actor=actor,
            overwrite=True,
            audit_details={
                "from_commit": stage.from_commit,
                "to_commit": stage.to_commit,
                "discarded_local_edits": discard_local_edits,
            },
        )
    finally:
        svc.staging.discard(stage.id)
    status = await _status(svc, updated)
    await svc.status_repo.put(
        status.with_(
            latest_commit=stage.to_commit, commits_ahead=0, files_changed=0, dismissed_commit=None
        )
    )
    return updated


async def keep_mine(svc: SkillSourceService, skill: Resource, commit: str | None) -> SourceStatus:
    """Stop offering ``commit`` (default: the latest one seen) for this skill."""
    source = git_source_of(skill)
    status = await _status(svc, skill)
    dismissed = commit or status.latest_commit
    if dismissed is None or dismissed == source.commit:
        return status
    return await svc.status_repo.put(status.with_(dismissed_commit=dismissed))


__all__ = [
    "CHECK_INTERVAL",
    "CommitLine",
    "CompareView",
    "UpdatePreview",
    "apply",
    "check",
    "check_due",
    "compare",
    "git_source_of",
    "keep_mine",
    "preview",
]
