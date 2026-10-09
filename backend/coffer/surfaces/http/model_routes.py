"""/api/v1/models — provider introspection routes.

The standalone model registry (CRUD) was retired when models + providers merged
into one LLM connection (a ``provider`` Resource). What remains here is the
read-only introspection the connection editors use: list the models a provider
exposes and probe a connection. Domain errors propagate to the app-wide handler
in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.provider.introspection import ModelIntrospectionService
from coffer.application.provider.introspection_gate import authorize_stored_key
from coffer.application.provider.ports import ModelList
from coffer.application.provider.service import ProviderService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import ProviderConfig
from coffer.infrastructure.provider.introspector import PROTOCOL_BASE_URLS
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.provider_dependencies import (
    get_introspection_service,
    get_provider_service,
)
from coffer.surfaces.http.provider_health_routes import get_provider_health_service_optional
from coffer.surfaces.http.provider_schemas import (
    ListModelsIn,
    ProviderModel,
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
    providers: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> ProviderModelsOut:
    """List the models a provider exposes (empty + message → enter manually).

    Each id comes back with a GUESSED modality so the connection's model table
    pre-fills a sensible kind; the user corrects it and the curated set stores
    the answer (spec provider-switching "Store a modality with each curated
    model").
    """
    await authorize_stored_key(
        providers,
        secret_ref=body.secret_ref,
        secret_value=body.secret_value,
        base_url=body.base_url,
        default_base_url=PROTOCOL_BASE_URLS.get(body.provider),
    )
    result = await svc.list_models(
        provider=body.provider,
        base_url=body.base_url,
        secret_ref=body.secret_ref,
        secret_value=body.secret_value,
    )
    await _keep_health(providers, body, result)
    return ProviderModelsOut(
        models=[ProviderModel(id=m.id, modality=m.modality) for m in result.models],
        message=result.message,
        reachable=result.reachable,
    )


async def _keep_health(providers: ProviderService, body: ListModelsIn, result: ModelList) -> None:
    """Keep the verdict of a listing that is a saved connection's own — its
    stored key, its URL, its wire (spec provider-switching "Know each
    connection's health without opening it"). A typed key, or a draft that
    differs from what is saved, says nothing about the saved connection."""
    health = get_provider_health_service_optional()
    if health is None or body.connection_uid is None or body.secret_value:
        return
    try:
        row = await providers.get(body.connection_uid)
    except ResourceNotFound:
        return
    cfg = ProviderConfig.model_validate(row.config)
    same = (
        cfg.protocol.value == body.provider
        and cfg.secret_ref == body.secret_ref
        and _norm(cfg.base_url) == _norm(body.base_url)
    )
    if same:
        await health.record_listing(row.uid, result)


def _norm(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


@router.post("/test-connection", response_model=TestResultOut)
async def test_connection(
    body: TestConnectionIn,
    svc: ModelIntrospectionService = Depends(get_introspection_service),  # noqa: B008
    providers: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> TestResultOut:
    """Probe a chat provider with a minimal request; 200 with ok=true/false."""
    await authorize_stored_key(
        providers,
        secret_ref=body.secret_ref,
        secret_value=body.secret_value,
        base_url=body.base_url,
        default_base_url=PROTOCOL_BASE_URLS.get(body.provider),
    )
    result = await svc.test_connection(
        provider=body.provider,
        model=body.model,
        base_url=body.base_url,
        secret_ref=body.secret_ref,
        secret_value=body.secret_value,
    )
    return TestResultOut(ok=result.ok, message=result.message, detail=result.detail)
