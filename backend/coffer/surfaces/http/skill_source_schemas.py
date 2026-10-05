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

from coffer.application.skill.source_change_ops import SourceChangePreview
from coffer.application.skill.staging import ImportStage, StagedSkill
from coffer.domain.skill.compare_url import compare_url
from coffer.domain.skill.folder_diff import FileChange
from coffer.domain.skill.requirements import CommandRequirement
from coffer.domain.skill.source import ArchiveImportSource, GitImportSource
from coffer.domain.skill.source_status import SourceStatus
from coffer.domain.skill.update_check import UpdateCheckChoice
from coffer.surfaces.http.handoff_schemas import HandoffOut

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
    #: The profiles that declare it; empty when SKILL.md itself does.
    profiles: list[str]


def requirement_out(r: CommandRequirement) -> SkillRequirementOut:
    return SkillRequirementOut(
        command=r.command, min_version=r.min_version, profiles=list(r.profiles)
    )


class SkillSecretRequirementOut(BaseModel):
    """One Coffer secret the skill's SKILL.md says it needs, and whether it is
    set in the secret store on this machine. Never a value."""

    name: str
    is_set: bool
    profiles: list[str]


class SkillToolRequirementOut(BaseModel):
    """One MCP server or custom-tool group the skill's SKILL.md says it calls
    (``requires: {tools: [...]}``), with its state now. Only names Coffer has
    are listed; an unknown one is skipped with a warning on the CLIs list."""

    name: str
    #: The server's or group's uid, for the link to its page.
    uid: str
    kind: Literal["mcp_server", "custom_tools"]
    #: ``off`` when it is switched off, ``failing`` when its last connection
    #: test failed, ``healthy`` otherwise.
    status: Literal["healthy", "off", "failing"]
    why: str | None
    profiles: list[str]


class SkillSkillRequirementOut(BaseModel):
    """One skill this one loads (``metadata.requires``)."""

    name: str
    #: The skill's uid; null when no skill by that name is in the library.
    uid: str | None
    found: bool
    #: Every agent this skill is delivered to also gets the required skill.
    delivered_to_same_agents: bool
    #: The agents that get this skill but not the required one.
    missing_agent_names: list[str]


class SkillCommitOut(BaseModel):
    id: str
    subject: str


class SkillSourceStatusOut(BaseModel):
    """What this machine last learned about a Git-imported skill's source."""

    checked_at: datetime | None
    last_success_at: datetime | None
    #: git's message from the last check; null when it reached the repository.
    error: str | None
    latest_commit: str | None
    commits_ahead: int
    files_changed: int
    #: The ref moved past the pin with commits that change the folder.
    update_available: bool
    #: The commits in the range with their subjects, shown where the source's
    #: host has no compare page.
    commits: list[SkillCommitOut]
    #: The compare page on the source's host (GitHub, GitLab) from the pin to
    #: ``latest_commit`` while an update is available; null for any other host.
    compare_url: str | None


def status_out(status: SourceStatus | None, source: GitImportSource) -> SkillSourceStatusOut:
    s = status or SourceStatus(skill_uid="")
    available = s.update_available(source.commit)
    return SkillSourceStatusOut(
        checked_at=s.checked_at,
        last_success_at=s.last_success_at,
        error=s.error,
        latest_commit=s.latest_commit,
        commits_ahead=s.commits_ahead,
        files_changed=s.files_changed,
        update_available=available,
        commits=[SkillCommitOut(id=i, subject=subject) for i, subject in s.commits]
        if available
        else [],
        compare_url=compare_url(source.url, source.commit, s.latest_commit)
        if available and s.latest_commit
        else None,
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


class SkillUpdateHandoffOut(BaseModel):
    """The newest commit upstream and the prompt that hands bringing it into
    the skill's master folder to the person's agent (spec skill-manager "Hand a
    Git-imported skill's update to an agent")."""

    commit: str
    handoff: HandoffOut


class SkillSourceChangeFileOut(BaseModel):
    """A file a change of source would add, remove or change — its name only."""

    path: str
    status: Literal["added", "removed", "modified"]


class SkillSourceChangeOut(BaseModel):
    """What moving the skill to another source would do, against its current
    folder. Staged until ``/source/change/apply`` or
    ``DELETE /skills/stage/{staging_id}``."""

    staging_id: str
    commit: str
    files: list[SkillSourceChangeFileOut]


class SkillSourceChangeApplyRequest(BaseModel):
    staging_id: str = Field(min_length=1)


def change_preview_out(p: SourceChangePreview) -> SkillSourceChangeOut:
    return SkillSourceChangeOut(
        staging_id=p.stage_id,
        commit=p.commit,
        files=[SkillSourceChangeFileOut(path=f.path, status=f.status) for f in p.files],  # type: ignore[arg-type]
    )


class SkillUpdateCheckSettingBody(BaseModel):
    """How often this machine checks Git-imported skills for updates in the
    background: every 6 hours, every day, every week, or only when asked."""

    interval: UpdateCheckChoice


class SkillUpdateMergedRequest(BaseModel):
    #: The upstream commit the skill's folder was merged with — the hand-off's
    #: ``commit``, in full or by a unique prefix of at least 7 characters.
    commit: str = Field(min_length=7, max_length=64)
