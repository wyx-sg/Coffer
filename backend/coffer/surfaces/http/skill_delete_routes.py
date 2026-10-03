"""DELETE /api/v1/skills/{uid} and POST /api/v1/skills/bulk-delete (spec
skill-manager "Refuse deleting a skill whose copy Coffer did not make", "Delete
a skill and keep a folder Coffer did not make").

A skill whose agent copy is a real folder, not Coffer's link, is refused
(``409 SKILL_COPY_NOT_OURS``). ``keep_foreign_copies`` goes ahead anyway: the
master and every Coffer link are removed, and each folder left alone is named in
the answer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from coffer.application.skill.copy_ops import KeptCopy
from coffer.application.skill.service import SkillService
from coffer.domain.error_base import CofferError
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.errors import details_of
from coffer.surfaces.http.skill_dependencies import get_skill_service

router = APIRouter(
    prefix="/api/v1/skills",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


def _actor(x_coffer_actor: str | None = Header(default=None)) -> str:
    return x_coffer_actor or "api"


class KeptCopyOut(BaseModel):
    """An agent's folder a delete left where it was."""

    agent_name: str
    path: str


class SkillDeleteOut(BaseModel):
    kept_copies: list[KeptCopyOut]


class SkillBulkDeleteIn(BaseModel):
    uids: list[str] = Field(min_length=1)
    #: Delete a skill even when an agent's copy is not Coffer's link, leaving
    #: that folder alone.
    keep_foreign_copies: bool = False


class SkillBulkDeleteResult(BaseModel):
    uid: str
    #: Empty when the skill is gone before the delete.
    name: str
    deleted: bool
    kept_copies: list[KeptCopyOut]
    #: Why it was not deleted (an error envelope's code, message and details);
    #: null when it was.
    error_code: str | None
    error_message: str | None
    error_details: dict[str, Any] | None


class SkillBulkDeleteOut(BaseModel):
    results: list[SkillBulkDeleteResult]


def _kept(items: list[KeptCopy]) -> list[KeptCopyOut]:
    return [KeptCopyOut(agent_name=k.agent_name, path=k.path) for k in items]


@router.delete("/{uid}", response_model=SkillDeleteOut)
async def delete_skill(
    uid: str,
    keep_foreign_copies: bool = False,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillDeleteOut:
    kept = await svc.remove(uid=uid, actor=actor, keep_foreign_copies=keep_foreign_copies)
    return SkillDeleteOut(kept_copies=_kept(kept))


@router.post("/bulk-delete", response_model=SkillBulkDeleteOut)
async def bulk_delete_skills(
    body: SkillBulkDeleteIn,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillBulkDeleteOut:
    """Delete each skill in turn; one that is refused never stops the others,
    and every skill gets its own result."""
    results: list[SkillBulkDeleteResult] = []
    for uid in body.uids:
        name = ""
        try:
            name = (await svc.get_skill(uid)).name
            kept = await svc.remove(
                uid=uid, actor=actor, keep_foreign_copies=body.keep_foreign_copies
            )
        except CofferError as exc:
            results.append(
                SkillBulkDeleteResult(
                    uid=uid,
                    name=name,
                    deleted=False,
                    kept_copies=[],
                    error_code=exc.code,
                    error_message=str(exc),
                    error_details=details_of(exc),
                )
            )
            continue
        results.append(
            SkillBulkDeleteResult(
                uid=uid,
                name=name,
                deleted=True,
                kept_copies=_kept(kept),
                error_code=None,
                error_message=None,
                error_details=None,
            )
        )
    return SkillBulkDeleteOut(results=results)
