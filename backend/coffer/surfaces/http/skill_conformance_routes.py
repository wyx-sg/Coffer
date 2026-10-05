"""POST /api/v1/skills/conformance/handoff — the prompt that hands a check of
one or more skills for suggestions to the person's agent (spec
skill-manager "Hand a skill's review to an agent"). Built from the
folders as they are when the button is pressed, so it is never stale."""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.application.skill.conformance_handoff import (
    ConformanceSkill,
    conformance_prompt,
    read_declared,
)
from coffer.application.skill.service import SkillService
from coffer.domain.skill.config import SkillConfig
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.skill_dependencies import get_skill_service

router = APIRouter(
    prefix="/api/v1/skills",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


class SkillConformanceHandoffIn(BaseModel):
    uids: list[str] = Field(min_length=1)


@router.post("/conformance/handoff", response_model=HandoffOut)
async def conformance_handoff(
    body: SkillConformanceHandoffIn,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
) -> HandoffOut:
    skills: list[ConformanceSkill] = []
    for uid in dict.fromkeys(body.uids):
        r = await svc.get_skill(uid)
        master = pathlib.Path(svc.master_path(r.name))
        skills.append(
            ConformanceSkill(
                name=r.name,
                master=master,
                declared=read_declared(master),
                source=SkillConfig.model_validate(r.config).source,
            )
        )
    return HandoffOut(prompt=conformance_prompt(skills))
