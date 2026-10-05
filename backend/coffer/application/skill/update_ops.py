"""Check a Git-imported skill's source for updates, and hand an update to an agent.

Spec skill-manager "Hand a Git-imported skill's update to an agent". A check
fetches into a staging directory it removes again and records what it found in
``skill_source_status``; the hand-off does the same fetch to learn the commit
range and the local edits, and answers the prompt that asks the person's agent
to bring the update into the master folder. Neither writes to the master store
or the pin: Coffer never applies an update itself.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from coffer.application.skill.staging import remove_dir
from coffer.application.skill.update_handoff import update_prompt
from coffer.domain.resource import Resource
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.content_hash import folder_content_hash
from coffer.domain.skill.folder_diff import diff_folders
from coffer.domain.skill.source import GitImportSource
from coffer.domain.skill.source_status import SourceStatus
from coffer.domain.skill_source_errors import (
    SkillNotFromGit,
    SkillSourceUnreachable,
    SkillUpdateNotPending,
)

if TYPE_CHECKING:
    from coffer.application.skill.source_service import SkillSourceService

#: Commit subjects kept on the check result, for a host with no compare page.
MAX_STATUS_COMMITS = 20


@dataclass(frozen=True)
class CommitLine:
    id: str
    subject: str


@dataclass(frozen=True)
class UpdateHandoff:
    """The newest commit upstream and the prompt that hands bringing it in to an agent."""

    commit: str
    prompt: str


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
        subjects: tuple[tuple[str, str], ...] = ()
        if latest == source.commit:
            commits, files = 0, 0
        else:
            found = await svc.git.commits(repo, source.commit, latest, source.subpath)
            commits = len(found)
            subjects = tuple((c.id, c.subject) for c in found[:MAX_STATUS_COMMITS])
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
            commits=subjects,
        )
    except SkillSourceUnreachable as exc:
        status = status.with_(checked_at=now, error=exc.git_message)
    finally:
        remove_dir(stage_dir)
        svc.staging.discard(stage_id)
    return await svc.status_repo.put(status)


async def check_due(
    svc: SkillSourceService, interval: timedelta, *, now: datetime | None = None
) -> int:
    """Check every Git-imported skill not checked within ``interval``; the count checked."""
    now = now or _now()
    statuses = await svc.status_repo.list_all()
    done = 0
    for skill in await svc.skills._rs.list(kind="skill"):
        try:
            git_source_of(skill)
        except SkillNotFromGit:
            continue
        last = statuses.get(skill.uid)
        if last is not None and last.checked_at is not None and now - last.checked_at < interval:
            continue
        await check(svc, skill)
        done += 1
    return done


async def handoff(svc: SkillSourceService, skill: Resource) -> UpdateHandoff:
    """The prompt that asks an agent to bring the skill's update into its master folder.

    Fetches upstream into a staging directory that is removed again, to learn
    the newest commit, the commits in range and the files edited locally since
    the pin. Refused ``SKILL_UPDATE_NOT_PENDING`` when no newer commit changes
    the skill's folder. Writes nothing to the master store or the pin.
    """
    source = git_source_of(skill)
    stage_id, stage_dir = svc.staging.new_dir()
    try:
        repo = stage_dir / "repo"
        await svc.git.clone(source.url, repo)
        latest = await svc.git.resolve(repo, source.ref, url=source.url)
        if latest == source.commit:
            raise SkillUpdateNotPending(skill.name, latest)
        pinned: pathlib.Path | None = None
        commits: list[CommitLine] = []
        if await svc.git.has_commit(repo, source.commit):
            commits = [
                CommitLine(c.id, c.subject)
                for c in await svc.git.commits(repo, source.commit, latest, source.subpath)
            ]
            if not commits:
                raise SkillUpdateNotPending(skill.name, latest)
            pinned = await svc.git.checkout(
                repo, source.commit, source.subpath, stage_dir / "pinned", url=source.url
            )
        master = pathlib.Path(svc.skills._store.paths_for(skill.name).folder)
        local = diff_folders(pinned, master) if _edited(svc, skill, source) else []
        prompt = update_prompt(
            name=skill.name,
            master=master,
            source=source,
            to_commit=latest,
            commits=commits,
            local_edits=[c.path for c in local],
        )
    finally:
        remove_dir(stage_dir)
        svc.staging.discard(stage_id)
    return UpdateHandoff(commit=latest, prompt=prompt)


__all__ = [
    "CommitLine",
    "UpdateHandoff",
    "check",
    "check_due",
    "git_source_of",
    "handoff",
]
