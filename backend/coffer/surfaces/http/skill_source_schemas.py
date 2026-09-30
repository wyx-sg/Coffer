"""Wire models for skill sources and upstream updates (spec skill-manager "Add
skills from an archive", "Add skills from a Git repository", "Update a
Git-imported skill from its source", "Show the commands a skill declares it
needs").

Split from ``skill_routes`` for the file-size cap. ``SkillOut`` itself stays
there; the source variants, the requirement and the update status it carries
are defined here and imported by it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from coffer.application.skill.staging import ImportStage, StagedSkill
from coffer.application.skill.update_ops import CompareView, UpdatePreview
from coffer.domain.skill.folder_diff import FileChange, TextVersion
from coffer.domain.skill.requires import SkillRequirement
from coffer.domain.skill.source import ArchiveImportSource, GitImportSource
from coffer.domain.skill.source_status import SourceStatus

# ---------- read-model parts ----------


class ArchiveImportSourceOut(BaseModel):
    """A skill unpacked from an uploaded archive; both fields are informational."""

    type: Literal["archive_import"]
    archive_name: str
    #: Where in the archive its SKILL.md sat; "" for the archive's top.
    folder: str


class GitImportSourceOut(BaseModel):
    """A skill copied from a folder of a Git repository at one pinned commit."""

    type: Literal["git_import"]
    url: str
    #: The branch, tag or commit asked for; null is the default branch.
    ref: str | None
    #: The skill's folder inside the repository; "" for the repository's top.
    subpath: str
    commit: str
    content_hash: str


def archive_source_out(s: ArchiveImportSource) -> ArchiveImportSourceOut:
    return ArchiveImportSourceOut(
        type="archive_import", archive_name=s.archive_name, folder=s.folder
    )


def git_source_out(s: GitImportSource) -> GitImportSourceOut:
    return GitImportSourceOut(
        type="git_import",
        url=s.url,
        ref=s.ref,
        subpath=s.subpath,
        commit=s.commit,
        content_hash=s.content_hash,
    )


class SkillRequirementOut(BaseModel):
    """One command the skill's SKILL.md says it needs."""

    command: str
    min_version: str | None


def requirement_out(r: SkillRequirement) -> SkillRequirementOut:
    return SkillRequirementOut(command=r.command, min_version=r.min_version)


class SkillSourceStatusOut(BaseModel):
    """What this machine last learned about a Git-imported skill's source."""

    checked_at: datetime | None
    last_success_at: datetime | None
    #: git's message from the last check; null when it reached the repository.
    error: str | None
    latest_commit: str | None
    commits_ahead: int
    files_changed: int
    dismissed_commit: str | None
    #: The ref moved past the pin with commits that change the folder, and
    #: the user did not choose Keep mine against that commit.
    update_available: bool


def status_out(status: SourceStatus | None, pinned: str) -> SkillSourceStatusOut:
    s = status or SourceStatus(skill_uid="")
    return SkillSourceStatusOut(
        checked_at=s.checked_at,
        last_success_at=s.last_success_at,
        error=s.error,
        latest_commit=s.latest_commit,
        commits_ahead=s.commits_ahead,
        files_changed=s.files_changed,
        dismissed_commit=s.dismissed_commit,
        update_available=s.update_available(pinned),
    )


# ---------- staging ----------


class SkillStageFolderRequest(BaseModel):
    path: str = Field(min_length=1)


class SkillStageGitRequest(BaseModel):
    url: str = Field(min_length=1)
    ref: str | None = None
    path: str | None = None


class StagedSkillOut(BaseModel):
    """One skill a stage found."""

    #: Where it sits in what was staged; "." for the top.
    folder: str
    #: From its SKILL.md; null when the folder does not validate.
    name: str | None
    description: str | None
    file_count: int
    size_bytes: int
    valid: bool
    reason: str | None
    message: str | None
    #: A skill of this name already exists; adding it means Replace.
    taken: bool
    #: The name is a skill Coffer generates, which nothing may replace.
    protected: bool


class SkillStagingOut(BaseModel):
    """What a staged folder, archive or repository holds. Nothing is written
    until ``POST /skills/stage/{staging_id}/confirm``."""

    staging_id: str
    kind: Literal["folder", "archive", "git"]
    #: The folder's path, the archive's file name, or the repository and subpath.
    label: str
    ref: str | None
    subpath: str
    #: Git only: the commit the ref resolved to, which a skill is pinned to.
    commit: str | None
    skills: list[StagedSkillOut]


def _staged_out(s: StagedSkill) -> StagedSkillOut:
    return StagedSkillOut(
        folder=s.folder,
        name=s.name,
        description=s.description,
        file_count=s.file_count,
        size_bytes=s.size_bytes,
        valid=s.valid,
        reason=s.reason,
        message=s.message,
        taken=s.taken,
        protected=s.protected,
    )


def staging_out(stage: ImportStage) -> SkillStagingOut:
    return SkillStagingOut(
        staging_id=stage.id,
        kind=stage.kind,
        label=stage.label,
        ref=stage.ref,
        subpath=stage.subpath,
        commit=stage.commit,
        skills=[_staged_out(s) for s in stage.skills],
    )


class SkillStagingConfirmRequest(BaseModel):
    #: The names to add, among the stage's valid skills.
    skills: list[str] = Field(min_length=1)
    #: Names that are taken and should be replaced in place.
    replace: list[str] = Field(default_factory=list)


# ---------- updates ----------


class SkillCommitOut(BaseModel):
    id: str
    subject: str


class SkillFileChangeOut(BaseModel):
    path: str
    status: Literal["added", "removed", "modified"]
    #: Unified diff; empty for a binary file.
    diff: str
    binary: bool
    additions: int
    deletions: int
    truncated: bool


def change_out(c: FileChange) -> SkillFileChangeOut:
    return SkillFileChangeOut(
        path=c.path,
        status=c.status,  # type: ignore[arg-type]
        diff=c.diff,
        binary=c.binary,
        additions=c.additions,
        deletions=c.deletions,
        truncated=c.truncated,
    )


class SkillUpdatePreviewOut(BaseModel):
    """What taking the source's newest commit would do. Staged until
    ``apply`` or ``DELETE /skills/stage/{staging_id}``."""

    staging_id: str
    from_commit: str
    to_commit: str
    #: The ref is still at the pinned commit.
    up_to_date: bool
    commits: list[SkillCommitOut]
    changes: list[SkillFileChangeOut]
    #: The folder was edited since the pin; applying discards the edit.
    conflict: bool
    #: The local edits, as changes from the pinned commit's folder.
    local_changes: list[SkillFileChangeOut]


def preview_out(p: UpdatePreview) -> SkillUpdatePreviewOut:
    return SkillUpdatePreviewOut(
        staging_id=p.stage_id,
        from_commit=p.from_commit,
        to_commit=p.to_commit,
        up_to_date=p.from_commit == p.to_commit,
        commits=[SkillCommitOut(id=c.id, subject=c.subject) for c in p.commits],
        changes=[change_out(c) for c in p.changes],
        conflict=p.conflict,
        local_changes=[change_out(c) for c in p.local_changes],
    )


class SkillTextVersionOut(BaseModel):
    #: Null when this version has no such file.
    text: str | None
    binary: bool
    truncated: bool


def _text(v: TextVersion) -> SkillTextVersionOut:
    return SkillTextVersionOut(text=v.text, binary=v.binary, truncated=v.truncated)


class SkillUpdateCompareOut(BaseModel):
    """One file in the master folder, the pinned commit and the new commit."""

    path: str
    local: SkillTextVersionOut
    pinned: SkillTextVersionOut
    incoming: SkillTextVersionOut


def compare_out(v: CompareView) -> SkillUpdateCompareOut:
    return SkillUpdateCompareOut(
        path=v.path, local=_text(v.local), pinned=_text(v.pinned), incoming=_text(v.incoming)
    )


class SkillUpdateApplyRequest(BaseModel):
    staging_id: str = Field(min_length=1)
    #: Take theirs: apply even though the folder was edited since the pin.
    discard_local_edits: bool = False


class SkillUpdateKeepRequest(BaseModel):
    #: The commit not to offer again; the latest one seen when omitted.
    commit: str | None = None
