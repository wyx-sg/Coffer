"""/api/v1/models — provider introspection routes.

The standalone model registry (CRUD) was retired when models + providers merged
into one LLM connection (a ``provider`` Resource). What remains here is the
read-only introspection the connection editors use: list the models a provider
exposes and probe a connection. Domain errors propagate to the app-wide handler
in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.providers.ports import ModelIntrospectionService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import get_introspection_service
from coffer.surfaces.http.chat.schemas import (
    ListModelsIn,
    ProviderModelsOut,
    TestConnectionIn,
    TestResultOut,
)

router = APIRouter(
    prefix="/api/v1/models",
    tags=["models"],
    dependencies=[Depends(require_token)],
)


@router.post("/list-models", response_model=ProviderModelsOut)
async def list_provider_models(
    body: ListModelsIn,
    svc: ModelIntrospectionService = Depends(get_introspection_service),  # noqa: B008
) -> ProviderModelsOut:
    """List the models a provider exposes (empty + message → enter manually)."""
    result = await svc.list_models(
        provider=body.provider,
        base_url=body.base_url,
        credential_ref=body.credential_ref,
        secret_value=body.secret_value,
    )
    return ProviderModelsOut(models=result.models, message=result.message)


@router.post("/test-connection", response_model=TestResultOut)
async def test_connection(
    body: TestConnectionIn,
    svc: ModelIntrospectionService = Depends(get_introspection_service),  # noqa: B008
) -> TestResultOut:
    """Probe a chat provider with a minimal request; 200 with ok=true/false."""
    result = await svc.test_connection(
        provider=body.provider,
        model=body.model,
        base_url=body.base_url,
        credential_ref=body.credential_ref,
        secret_value=body.secret_value,
    )
    return TestResultOut(ok=result.ok, message=result.message, detail=result.detail)
