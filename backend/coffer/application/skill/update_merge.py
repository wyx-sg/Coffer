"""Merge an upstream update into a skill's local edits, with an agent.

Spec skill-manager "Update a Git-imported skill from its source" offers two
answers to an update that meets local edits — keep mine, take theirs — and
neither merges. The merge itself is a chore for the person's agent: the
preview's conflict carries a hand-off (``update_handoff``) that names the
master folder, the edited files, the commit range and where upstream can be
read; the agent edits the master folder only, and the person then records it
with **I merged it** (:func:`mark_merged`, spec skill-manager "Record an
update merged into local edits").

Recording moves the pin to the upstream commit the merge was made against and
nothing else: the master's files stay as the agent left them. The pin's
content hash becomes that commit's own content, so the merged folder still
reads as edited against its new base — which is what it is: the person's
edits, carried onto upstream. A later update is then a conflict again, with
exactly those edits listed, rather than one that silently overwrites them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.skill import update_ops
from coffer.application.skill.staging import remove_dir
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.content_hash import folder_content_hash
from coffer.domain.skill.source_status import SourceStatus
from coffer.domain.skill_source_errors import SkillUpdateNotPending

if TYPE_CHECKING:
    from coffer.application.skill.source_service import SkillSourceService


def _match(commit: str, pending: list[str]) -> str | None:
    """The one pending commit ``commit`` names in full or by a unique prefix."""
    wanted = commit.strip().lower()
    if len(wanted) < 7:
        return None
    found = [c for c in dict.fromkeys(pending) if c.lower().startswith(wanted)]
    return found[0] if len(found) == 1 else None


async def mark_merged(
    svc: SkillSourceService, skill: Resource, commit: str, *, actor: str
) -> Resource:
    """Move the pin to ``commit`` without touching the master's files.

    ``commit`` must be an update waiting for the skill: the ref's newest commit,
    or one of the commits between the pin and it that change the skill's
    folder. The repository is fetched again, so the pin's content hash is
    that commit's own content.
    """
    source = update_ops.git_source_of(skill)
    stage_id, stage_dir = svc.staging.new_dir()
    try:
        repo = stage_dir / "repo"
        await svc.git.clone(source.url, repo)
        latest = await svc.git.resolve(repo, source.ref, url=source.url)
        pending: list[str] = []
        if latest != source.commit:
            pending.append(latest)
            if await svc.git.has_commit(repo, source.commit):
                found = await svc.git.commits(repo, source.commit, latest, source.subpath)
                pending += [c.id for c in found]
        target = _match(commit, [c for c in pending if c != source.commit])
        if target is None:
            raise SkillUpdateNotPending(skill.name, commit)
        folder = await svc.git.checkout(
            repo, target, source.subpath, stage_dir / "merged", url=source.url
        )
        content_hash = folder_content_hash(folder)
    finally:
        remove_dir(stage_dir)
        svc.staging.discard(stage_id)

    cfg = SkillConfig.model_validate(skill.config)
    cfg = cfg.model_copy(
        update={
            "source": source.model_copy(update={"commit": target, "content_hash": content_hash})
        }
    )
    updated = await svc.skills._rs.update_config(
        skill.uid,
        new_config=cfg.model_dump(mode="json"),
        actor=actor,
        allow_lifecycle_kind=True,  # only the pin moves; the master is untouched
    )
    await svc.skills._audit.record(
        AuditEventType.SKILL_UPDATE_MERGED.value,
        resource=updated,
        actor=actor,
        details={"from_commit": source.commit, "to_commit": target},
    )
    if target == latest:
        status = await svc.status_repo.get(skill.id) or SourceStatus(skill_resource_id=skill.id)
        await svc.status_repo.put(
            status.with_(
                latest_commit=latest, commits_ahead=0, files_changed=0, dismissed_commit=None
            )
        )
    else:
        # Merged against a commit upstream has since moved past: what is
        # still ahead of the new pin is counted by a fresh check.
        await update_ops.check(svc, updated)
    return updated


__all__ = ["mark_merged"]
