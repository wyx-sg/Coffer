# backend/coffer/surfaces/http/embedding_routes.py
"""/api/v1/embedding/config — the single, global embedding configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.embedding_config_service import EmbeddingConfigService
from coffer.domain.embedding_config import GlobalEmbeddingConfig
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_embedding_config_service
from coffer.surfaces.http.schemas import EmbeddingConfigOut, EmbeddingConfigUpdate

router = APIRouter(
    prefix="/api/v1/embedding",
    tags=["embedding"],
    dependencies=[Depends(require_token)],
)


def _to_out(cfg: GlobalEmbeddingConfig) -> EmbeddingConfigOut:
    return EmbeddingConfigOut(
        enabled=cfg.enabled,
        provider=cfg.provider,
        model=cfg.model,
        base_url=cfg.base_url,
        credential_ref=cfg.credential_ref,
        dimensions=cfg.dimensions,
        updated_at=cfg.updated_at,
    )


@router.get("/config", response_model=EmbeddingConfigOut)
async def get_config(
    svc: EmbeddingConfigService = Depends(get_embedding_config_service),  # noqa: B008
) -> EmbeddingConfigOut:
    return _to_out(await svc.get())


@router.put("/config", response_model=EmbeddingConfigOut)
async def update_config(
    body: EmbeddingConfigUpdate,
    svc: EmbeddingConfigService = Depends(get_embedding_config_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> EmbeddingConfigOut:
    saved = await svc.update(
        enabled=body.enabled,
        provider=body.provider,
        model=body.model,
        base_url=body.base_url,
        credential_ref=body.credential_ref,
        dimensions=body.dimensions,
        actor=actor,
    )
    return _to_out(saved)
