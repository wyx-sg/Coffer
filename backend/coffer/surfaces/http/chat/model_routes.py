"""/api/v1/models — model config CRUD routes.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from coffer.application.chat.model_service import ModelService
from coffer.domain.chat.model import ModelConfig
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.schemas import (
    ModelCreate,
    ModelListOut,
    ModelOut,
    ModelPatch,
)
from coffer.surfaces.http.dependencies import get_model_service

router = APIRouter(
    prefix="/api/v1/models",
    tags=["models"],
    dependencies=[Depends(require_token)],
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _model_out(m: ModelConfig) -> ModelOut:
    return ModelOut(
        id=m.id,
        display_name=m.display_name,
        provider=str(m.provider),  # type: ignore[arg-type]
        model=m.model,
        credential_ref=m.credential_ref,
        base_url=m.base_url,
        is_default=m.is_default,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=ModelListOut)
async def list_models(
    svc: ModelService = Depends(get_model_service),  # noqa: B008
) -> ModelListOut:
    """List all configured models."""
    models = await svc.list()
    return ModelListOut(models=[_model_out(m) for m in models])


@router.post("", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
async def create_model(
    body: ModelCreate,
    svc: ModelService = Depends(get_model_service),  # noqa: B008
) -> ModelOut:
    """Register a new model config.  Returns 400 on validation failure."""
    m = await svc.create(
        display_name=body.display_name,
        provider=body.provider,
        model=body.model,
        credential_ref=body.credential_ref,
        base_url=body.base_url,
        is_default=body.is_default,
    )
    return _model_out(m)


@router.patch("/{id}", response_model=ModelOut)
async def update_model(
    id: str,
    body: ModelPatch,
    svc: ModelService = Depends(get_model_service),  # noqa: B008
) -> ModelOut:
    """Partially update a model config.  Returns 404 / 400 on errors."""
    m = await svc.update(
        id,
        display_name=body.display_name,
        model=body.model,
        credential_ref=body.credential_ref,
        base_url=body.base_url,
        is_default=body.is_default,
    )
    return _model_out(m)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_model(
    id: str,
    svc: ModelService = Depends(get_model_service),  # noqa: B008
) -> Response:
    """Remove a model config.  Returns 404 if not found."""
    await svc.delete(id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
