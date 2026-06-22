# backend/coffer/surfaces/http/internal_engine_routes.py
"""/api/v1/internal-engine-config — the single, global internal-engine model.

Coffer's internal LLM engine (organizer / reorg / distill / ``coffer__ask``)
takes its endpoint + key from the ``internal_default`` connection but its MODEL
from this singleton (spec 011 amendment 2026-06-22b). The connection no longer
owns the internal-engine model."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_internal_engine_config_service
from coffer.surfaces.http.schemas import InternalEngineConfigOut, InternalEngineConfigUpdate

router = APIRouter(
    prefix="/api/v1/internal-engine-config",
    tags=["internal-engine"],
    dependencies=[Depends(require_token)],
)


def _to_out(cfg: GlobalInternalEngineConfig) -> InternalEngineConfigOut:
    return InternalEngineConfigOut(model=cfg.model, updated_at=cfg.updated_at)


@router.get("", response_model=InternalEngineConfigOut)
async def get_config(
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
) -> InternalEngineConfigOut:
    return _to_out(await svc.get())


@router.put("", response_model=InternalEngineConfigOut)
async def update_config(
    body: InternalEngineConfigUpdate,
    svc: InternalEngineConfigService = Depends(get_internal_engine_config_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> InternalEngineConfigOut:
    return _to_out(await svc.update(model=body.model, actor=actor))
