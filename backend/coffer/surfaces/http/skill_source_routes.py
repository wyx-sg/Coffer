"""/api/v1/skills/stage/* and /api/v1/skills/{uid}/source/* — where a skill
comes from (spec skill-manager "Add skills from an archive", "Add skills from
a Git repository", "Hand a Git-imported skill's update to an agent").

A stage is read-only until its confirm: the three ``stage`` routes answer what
they found, ``confirm`` registers the chosen skills, and ``DELETE`` removes the
stage — the web dialog calls it when it closes, the CLI when the user answers
no. An update preview is a stage too, so the same ``DELETE`` closes it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from pydantic import BaseModel

from coffer.application.skill.service import SkillService
from coffer.application.skill.source_service import SkillSourceService
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.source import GitImportSource
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.skill_dependencies import get_skill_service, get_skill_source_service
from coffer.surfaces.http.skill_routes import SkillOut, _actor, _agents_by_uid, _to_skill_out
from coffer.surfaces.http.skill_source_schemas import (
    SkillSourceChangeApplyRequest,
    SkillSourceChangeOut,
    SkillSourceStatusOut,
    SkillStageFolderRequest,
    SkillStageGitRequest,
    SkillStagingConfirmRequest,
    SkillStagingOut,
    SkillUpdateCheckSettingBody,
    SkillUpdateHandoffOut,
    SkillUpdateMergedRequest,
    change_preview_out,
    staging_out,
    status_out,
)

router = APIRouter(
    prefix="/api/v1/skills",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


class SkillStagingConfirmOut(BaseModel):
    """The skills a confirm added (or replaced), as the read model shows them."""

    items: list[SkillOut]


# ---------- staging an import ----------


@router.post("/stage/folder", response_model=SkillStagingOut, status_code=status.HTTP_201_CREATED)
async def stage_folder(
    body: SkillStageFolderRequest,
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillStagingOut:
    return staging_out(await sources.stage_folder(body.path))


@router.post("/stage/archive", response_model=SkillStagingOut, status_code=status.HTTP_201_CREATED)
async def stage_archive(
    file: UploadFile = File(...),  # noqa: B008
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillStagingOut:
    try:
        return staging_out(await sources.stage_archive(file.file, file.filename or "archive.zip"))
    finally:
        await file.close()


@router.post("/stage/git", response_model=SkillStagingOut, status_code=status.HTTP_201_CREATED)
async def stage_git(
    body: SkillStageGitRequest,
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillStagingOut:
    return staging_out(await sources.stage_git(body.url, body.ref, body.path))


@router.post(
    "/stage/{staging_id}/confirm",
    response_model=SkillStagingConfirmOut,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_stage(
    staging_id: str,
    body: SkillStagingConfirmRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillStagingConfirmOut:
    added = await sources.confirm(staging_id, names=body.skills, replace=body.replace, actor=actor)
    agents = await _agents_by_uid(svc)
    return SkillStagingConfirmOut(
        items=[await _to_skill_out(svc, r, agents, sources=sources) for r in added]
    )


@router.delete(
    "/stage/{staging_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def cancel_stage(
    staging_id: str,
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> Response:
    # Idempotent: a stage already confirmed, cancelled or expired is gone,
    # which is what the caller wanted.
    sources.cancel(staging_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- a Git-imported skill's updates ----------


@router.get("/update-check", response_model=SkillUpdateCheckSettingBody)
async def get_update_check(
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillUpdateCheckSettingBody:
    """How often this machine checks skills for updates in the background."""
    return SkillUpdateCheckSettingBody(interval=sources.update_check_choice())


@router.put("/update-check", response_model=SkillUpdateCheckSettingBody)
async def put_update_check(
    body: SkillUpdateCheckSettingBody,
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillUpdateCheckSettingBody:
    """Choose it; kept in ``~/.coffer/daemon-config.json`` and in effect at once."""
    return SkillUpdateCheckSettingBody(interval=sources.set_update_check_choice(body.interval))


@router.post("/{uid}/source/check", response_model=SkillSourceStatusOut)
async def check_source(
    uid: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillSourceStatusOut:
    result = await sources.check(uid)
    source = SkillConfig.model_validate((await svc.get_skill(uid)).config).source
    assert isinstance(source, GitImportSource)  # check() refused any other source
    return status_out(result, source)


@router.post("/{uid}/source/handoff", response_model=SkillUpdateHandoffOut)
async def hand_off_update(
    uid: str,
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillUpdateHandoffOut:
    """The prompt that hands the skill's update to the person's agent (spec
    skill-manager "Hand a Git-imported skill's update to an agent"); refused
    ``SKILL_UPDATE_NOT_PENDING`` when no update is available. Writes nothing."""
    result = await sources.handoff(uid)
    return SkillUpdateHandoffOut(commit=result.commit, handoff=HandoffOut(prompt=result.prompt))


@router.post("/{uid}/source/change", response_model=SkillSourceChangeOut)
async def preview_source_change(
    uid: str,
    body: SkillStageGitRequest,
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillSourceChangeOut:
    """Stage a new repository / ref / folder for this skill and name the files
    that would change; ``/source/change/apply`` with the stage takes it."""
    return change_preview_out(await sources.change_source(uid, body.url, body.ref, body.path))


@router.post("/{uid}/source/change/apply", response_model=SkillOut)
async def apply_source_change(
    uid: str,
    body: SkillSourceChangeApplyRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    updated = await sources.apply_change(uid, body.staging_id, actor=actor)
    return await _to_skill_out(svc, updated, await _agents_by_uid(svc), sources=sources)


@router.post("/{uid}/source/merged", response_model=SkillOut)
async def record_merged(
    uid: str,
    body: SkillUpdateMergedRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    """ "I merged it" (spec skill-manager "Record an update merged into local
    edits"): pin the skill to the upstream commit its local edits were merged
    with, leaving the master folder's files as they are."""
    updated = await sources.mark_merged(uid, body.commit, actor=actor)
    return await _to_skill_out(svc, updated, await _agents_by_uid(svc), sources=sources)
