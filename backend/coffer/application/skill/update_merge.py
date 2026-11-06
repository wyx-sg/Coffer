"""Record an update the person's agent merged into the master folder.

Spec skill-manager "Record an update merged into local edits". The agent
brings the update in after the hand-off of "Hand a Git-imported skill's update
to an agent" (``update_handoff``); the person then records it with **I merged
it** (:func:`mark_merged`).

Recording moves the pin to the upstream commit the merge was made against and
nothing else: the master's files stay as the agent left them. The pin's
content hash becomes that commit's own content, so the merged folder still
reads as edited against its new base — which is what it is: the person's
edits, carried onto upstream. The next update's hand-off then lists exactly
those edits, rather than the update silently overwriting them.
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


async def mark_merged(
    svc: SkillSourceService, skill: Resource, commit: str, *, actor: str
) -> Resource:
    """Move the pin to ``commit`` without touching the master's files.

    ``commit`` must be the update the skill is offered, the ref's newest
    commit, given in full: the hand-off asks the agent to merge exactly that
    one. The repository is fetched again, so the pin's content hash is that
    commit's own content.
    """
    source = update_ops.git_source_of(skill)
    stage_id, stage_dir = svc.staging.new_dir()
    try:
        repo = stage_dir / "repo"
        await svc.git.clone(source.url, repo)
        latest = await svc.git.resolve(repo, source.ref, url=source.url)
        if latest == source.commit or commit.strip().lower() != latest.lower():
            raise SkillUpdateNotPending(skill.name, commit)
        target = latest
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
    status = await svc.status_repo.get(skill.uid) or SourceStatus(skill_uid=skill.uid)
    await svc.status_repo.put(
        status.with_(latest_commit=latest, commits_ahead=0, files_changed=0, commits=())
    )
    return updated


__all__ = ["mark_merged"]
