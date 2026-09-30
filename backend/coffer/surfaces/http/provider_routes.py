"""/api/v1/providers — provider-profile CRUD + switch (spec provider-switching).

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from coffer.application.provider.order_ops import ProviderOrderError
from coffer.application.provider.prices import ProviderPriceResolver
from coffer.application.provider.service import ProviderService
from coffer.application.provider.targets import scoped_targets
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import CuratedModel, ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.usage.pricing import ResolvedPrice
from coffer.infrastructure.provider import local_runtime
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_resource_service
from coffer.surfaces.http.provider_dependencies import get_price_resolver, get_provider_service
from coffer.surfaces.http.provider_schemas import (
    ActivateOut,
    DeactivateOut,
    DetectLocalIn,
    DetectLocalOut,
    LocalModelOut,
    LocalRuntimeOut,
    ModelPriceOut,
    ModelPricesIn,
    ModelPricesOut,
    ProviderCreate,
    ProviderListOut,
    ProviderModel,
    ProviderOrderIn,
    ProviderOut,
    ProviderPatch,
)

router = APIRouter(
    prefix="/api/v1/providers",
    tags=["providers"],
    dependencies=[Depends(require_token)],
)


def _curated(models: list[ProviderModel] | None) -> list[CuratedModel] | None:
    """Wire entries → the domain's curated set (``None`` leaves the set alone)."""
    if models is None:
        return None
    return [
        CuratedModel(
            id=m.id,
            modality=m.modality,
            context_window=m.context_window,
            effort_levels=m.effort_levels,
            default_effort=m.default_effort,
            price=m.price,
        )
        for m in models
    ]


def price_out(model: str, resolved: ResolvedPrice | None) -> ModelPriceOut:
    """One model's resolved price on the wire (its base tier)."""
    if resolved is None:
        return ModelPriceOut(model=model)
    p = resolved.price
    return ModelPriceOut(
        model=model,
        source=resolved.source,
        source_name=resolved.source_name,
        input=p.input,
        output=p.output,
        cache_write_5m=p.cache_write_5m,
        cache_write_1h=p.cache_write_1h,
        cache_read=p.cache_read,
        tiered=bool(p.tiers),
    )


def _provider_out(resource: Resource, agents: list[Resource]) -> ProviderOut:
    """One connection on the wire.

    ``agents`` is the whole agent registry, and it is a parameter rather than
    something fetched in here because a scope holds agent UIDS: resolving them
    into the agent TYPES ``compatible_agents`` reports needs the rows, and the
    list route projects many connections against the same registry. Passing it
    in is what keeps that one read per request instead of one per row.

    The rows come from ``ResourceService.list(kind="agent")``, not from the
    agent kind's own service. "Which resources are of kind agent" is a
    kind-agnostic question the framework answers, and asking it that way is
    what keeps this module — one kind's surface — from importing another
    kind's, which the import contracts forbid for exactly this reason.
    """
    cfg = ProviderConfig.model_validate(resource.config)
    return ProviderOut(
        uid=resource.uid,
        name=resource.name,
        title=resource.title,
        protocol=cfg.protocol,
        base_url=cfg.base_url,
        credential_ref=cfg.credential_ref,
        # Reported, never accepted: the reach comes from the resource's
        # per-agent scope (ADR per-agent-resource-scope). This is the CONFIGURED
        # reach, not the effective projection — ``enabled`` rides the same
        # payload (below), so a client that wants the intersection can take it,
        # while the management surface can still render the agent list of a
        # connection the user has switched off. Folding ``enabled`` in here
        # instead made those chips empty on disable, which reads as erased data.
        compatible_agents=scoped_targets(resource, cfg, agents),
        models=[
            ProviderModel(
                id=m.id,
                modality=m.modality,
                context_window=m.context_window,
                effort_levels=m.effort_levels,
                default_effort=m.default_effort,
                price=m.price,
            )
            for m in cfg.models
        ],
        is_active=cfg.is_active,
        local_runtime=cfg.local_runtime,
        fallback=cfg.fallback,
        internal_default=cfg.internal_default,
        transcribe_default=cfg.transcribe_default,
        enabled=resource.enabled,
        description=resource.description,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )


@router.get("", response_model=ProviderListOut)
async def list_providers(
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ProviderListOut:
    """List all provider profiles."""
    rows = await svc.list()
    # One registry read for the whole page, not one per connection: every row's
    # ``compatible_agents`` resolves its scope's agent uids against the same
    # list.
    registry = await resources.list(kind="agent")
    return ProviderListOut(providers=[_provider_out(r, registry) for r in rows])


@router.post("/detect-local", response_model=DetectLocalOut)
async def detect_local(body: DetectLocalIn) -> DetectLocalOut:
    """Which local model runtime answers where (spec provider-switching
    "Detect a local model runtime without changing it"). Read-only probes of
    loopback addresses only; nothing is pulled or loaded. A non-loopback URL
    is refused as 422."""
    try:
        if body.base_url:
            hit = await local_runtime.detect(body.base_url)
            found = [hit] if hit is not None else []
        else:
            found = await local_runtime.detect_defaults()
    except local_runtime.NotLoopbackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DetectLocalOut(
        found=[
            LocalRuntimeOut(
                base_url=d.base_url,
                runtime=d.runtime,
                models=[
                    LocalModelOut(id=m.id, context_window=m.context_window, tools=m.tools)
                    for m in d.models
                ],
            )
            for d in found
        ]
    )


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: ProviderCreate,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderOut:
    """Create a provider profile (422 when the credential source is invalid)."""
    resource = await svc.create(
        body.name,
        protocol=body.protocol,
        base_url=body.base_url,
        secret_value=body.secret_value,
        credential_ref=body.credential_ref,
        models=_curated(body.models),
        description=body.description,
        local_runtime=body.local_runtime,
        actor=actor,
    )
    return _provider_out(resource, await resources.list(kind="agent"))


@router.get("/{uid}", response_model=ProviderOut)
async def get_provider(
    uid: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ProviderOut:
    """Get one provider profile (404 if absent)."""
    return _provider_out(await svc.get(uid), await resources.list(kind="agent"))


@router.patch("/{uid}", response_model=ProviderOut)
async def update_provider(
    uid: str,
    body: ProviderPatch,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderOut:
    """Partially update a provider profile."""
    resource = await svc.update(
        uid,
        protocol=body.protocol,
        base_url=body.base_url,
        secret_value=body.secret_value,
        models=_curated(body.models),
        description=body.description,
        fallback=body.fallback,
        actor=actor,
    )
    return _provider_out(resource, await resources.list(kind="agent"))


@router.put("/order", response_model=ProviderListOut)
async def reorder_providers(
    body: ProviderOrderIn,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderListOut:
    """Reorder the Model providers list — the order fallbacks are tried in
    (spec provider-switching "Order providers, and fail over in that order").
    422 unless ``uids`` names every provider exactly once."""
    try:
        rows = await svc.reorder(body.uids, actor=actor)
    except ProviderOrderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    registry = await resources.list(kind="agent")
    return ProviderListOut(providers=[_provider_out(r, registry) for r in rows])


@router.post("/{uid}/prices", response_model=ModelPricesOut)
async def model_prices(
    uid: str,
    body: ModelPricesIn,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    resolver: ProviderPriceResolver = Depends(get_price_resolver),  # noqa: B008
) -> ModelPricesOut:
    """Each model's price on this provider, with its source: You set, From
    <provider>, Bundled or local — or none (spec provider-switching "Resolve
    each model's price from the provider, its API, or the bundled list").
    Read-only; nothing is fetched from the network."""
    await svc.get(uid)
    resolved = await resolver.resolve_many(uid, body.models)
    return ModelPricesOut(
        prices=[price_out(model, r) for model, r in resolved.items()],
        bundled_version=resolver.bundled_version,
    )


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_provider(
    uid: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Delete a provider profile (404 if absent)."""
    await svc.delete(uid, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{uid}/activate", response_model=ActivateOut)
async def activate_provider(
    uid: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ActivateOut:
    """Switch: make this profile active for its wire format and project it."""
    result = await svc.activate(uid, actor=actor)
    return ActivateOut(
        activated=result.activated,
        protocol=result.protocol,  # type: ignore[arg-type]
        projected=result.projected,
        skipped=result.skipped,
    )


@router.post("/use-builtin/{agent_type}", response_model=DeactivateOut)
async def use_builtin_provider(
    agent_type: AgentType,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DeactivateOut:
    """Switch every agent of this type back to its OWN built-in login: remove
    Coffer's projection from the native config and clear the active connection
    covering it. Idempotent — a no-op when the agent already runs built-in."""
    result = await svc.deactivate(agent_type, actor=actor)
    return DeactivateOut(
        agent_type=AgentType(result.agent_type),
        deprojected=result.deprojected,
        previous=result.previous,
    )


@router.post("/{uid}/internal-default", response_model=ProviderOut)
async def set_internal_default_provider(
    uid: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderOut:
    """Make this connection Coffer's internal-engine default (≤1 globally).

    Clears the flag on every other connection first, so setting a new default
    moves it off the previous one. 404 if the connection is absent.
    """
    updated = await svc.set_internal_default(uid, actor=actor)
    return _provider_out(updated, await resources.list(kind="agent"))


@router.post("/{uid}/transcribe-default", response_model=ProviderOut)
async def set_transcribe_default_provider(
    uid: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> ProviderOut:
    """Make this connection the one Coffer transcribes speech on (≤1 globally).

    The twin of the route above, and deliberately a SECOND flag rather than a
    reuse of it: the two are different models, and a chat gateway commonly
    serves no ``/audio/transcriptions`` at all. Nothing falls back between
    them — with no connection marked here, Coffer transcribes nothing and hands
    the agent the audio file untouched. 404 if the connection is absent.
    """
    updated = await svc.set_transcribe_default(uid, actor=actor)
    return _provider_out(updated, await resources.list(kind="agent"))
