"""/api/v1/catalog/skills* — skill discovery (browse + install), spec 005.

Browse/search the bundled starter catalog and install an entry. Install reuses
the main skills router's SkillOut mapper and the SkillService Git-fetch path
(SSRF guard + AgentSkills validation + content scan).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from coffer.application.skill.catalog_ops import browse_catalog, install_from_catalog
from coffer.application.skill.service import SkillService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_skill_service
from coffer.surfaces.http.skill_routes import (
    SkillOut,
    _actor,
    _agents_by_id,
    _to_skill_out,
    _validate_skill_name,
)

router = APIRouter(
    prefix="/api/v1/catalog",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


class CatalogEntryOut(BaseModel):
    name: str
    description: str
    git_url: str
    git_ref: str
    git_subpath: str
    publisher: str


class CatalogListOut(BaseModel):
    items: list[CatalogEntryOut]


@router.get("/skills", response_model=CatalogListOut)
async def list_catalog(q: str | None = Query(default=None)) -> CatalogListOut:
    return CatalogListOut(
        items=[
            CatalogEntryOut(
                name=e.name,
                description=e.description,
                git_url=e.git_url,
                git_ref=e.git_ref,
                git_subpath=e.git_subpath,
                publisher=e.publisher,
            )
            for e in browse_catalog(q)
        ]
    )


@router.post("/skills/{name}/install", response_model=SkillOut, status_code=201)
async def install_catalog_skill(
    name: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    name = _validate_skill_name(name)
    r = await install_from_catalog(service=svc, name=name, actor=actor)
    return await _to_skill_out(svc, r, await _agents_by_id(svc))
