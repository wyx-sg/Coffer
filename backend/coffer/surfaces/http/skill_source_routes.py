"""/api/v1/skills/stage/* and /api/v1/skills/{uid}/source/* — where a skill
comes from (spec skill-manager "Add skills from an archive", "Add skills from
a Git repository", "Update a Git-imported skill from its source").

A stage is read-only until its confirm: the three ``stage`` routes answer what
they found, ``confirm`` registers the chosen skills, and ``DELETE`` removes the
stage — the web dialog calls it when it closes, the CLI when the user answers
no. An update preview is a stage too, so the same ``DELETE`` closes it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from pydantic import BaseModel

from coffer.application.skill.service import SkillService
from coffer.application.skill.source_service import SkillSourceService
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.source import GitImportSource
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.skill_dependencies import get_skill_service, get_skill_source_service
from coffer.surfaces.http.skill_routes import SkillOut, _actor, _agents_by_uid, _to_skill_out
from coffer.surfaces.http.skill_source_schemas import (
    SkillSourceStatusOut,
    SkillStageFolderRequest,
    SkillStageGitRequest,
    SkillStagingConfirmRequest,
    SkillStagingOut,
    SkillUpdateApplyRequest,
    SkillUpdateCompareOut,
    SkillUpdateKeepRequest,
    SkillUpdatePreviewOut,
    compare_out,
    preview_out,
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


@router.post("/{uid}/source/check", response_model=SkillSourceStatusOut)
async def check_source(
    uid: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillSourceStatusOut:
    result = await sources.check(uid)
    source = SkillConfig.model_validate((await svc.get_skill(uid)).config).source
    assert isinstance(source, GitImportSource)  # check() refused any other source
    return status_out(result, source.commit)


@router.post("/{uid}/source/preview", response_model=SkillUpdatePreviewOut)
async def preview_update(
    uid: str,
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillUpdatePreviewOut:
    return preview_out(await sources.preview(uid))


@router.get("/{uid}/source/compare", response_model=SkillUpdateCompareOut)
async def compare_update(
    uid: str,
    staging_id: str = Query(..., min_length=1),
    path: str = Query(..., min_length=1),
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillUpdateCompareOut:
    return compare_out(await sources.compare(uid, staging_id, path))


@router.post("/{uid}/source/apply", response_model=SkillOut)
async def apply_update(
    uid: str,
    body: SkillUpdateApplyRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    updated = await sources.apply(
        uid, body.staging_id, discard_local_edits=body.discard_local_edits, actor=actor
    )
    return await _to_skill_out(svc, updated, await _agents_by_uid(svc), sources=sources)


@router.post("/{uid}/source/keep", response_model=SkillSourceStatusOut)
async def keep_mine(
    uid: str,
    body: SkillUpdateKeepRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService = Depends(get_skill_source_service),  # noqa: B008
) -> SkillSourceStatusOut:
    result = await sources.keep_mine(uid, body.commit)
    source = SkillConfig.model_validate((await svc.get_skill(uid)).config).source
    assert isinstance(source, GitImportSource)
    return status_out(result, source.commit)
