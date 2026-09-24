"""/api/v1/providers — provider-profile CRUD + switch (spec provider-switching).

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from coffer.application.provider.service import ProviderService
from coffer.application.provider.targets import scoped_targets
from coffer.application.resource_service import ResourceService
from coffer.domain.provider.config import CuratedModel, Protocol, ProviderConfig
from coffer.domain.resource import Resource
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_resource_service
from coffer.surfaces.http.provider_dependencies import get_provider_service
from coffer.surfaces.http.provider_schemas import (
    ActivateOut,
    ActiveKeyOut,
    DeactivateOut,
    ProviderCreate,
    ProviderListOut,
    ProviderModel,
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
    return [CuratedModel(id=m.id, modality=m.modality) for m in models]


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
        models=[ProviderModel(id=m.id, modality=m.modality) for m in cfg.models],
        is_active=cfg.is_active,
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
        actor=actor,
    )
    return _provider_out(resource, await resources.list(kind="agent"))


@router.get("/active-key/{wire}", response_model=ActiveKeyOut)
async def active_provider_key(
    wire: Protocol,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> ActiveKeyOut:
    """Back-compat: the decrypted key of the connection active for ``wire``'s
    agent (legacy ``--wire`` helper). 404 when none. New projections use
    ``GET /{uid}/key`` instead, which names the connection directly."""
    return ActiveKeyOut(value=await svc.resolve_active_key(wire))


@router.get("/{uid}/key", response_model=ActiveKeyOut)
async def connection_key(
    uid: str,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
) -> ActiveKeyOut:
    """The decrypted key of a SPECIFIC connection — what Claude Code's projected
    ``apiKeyHelper`` (``coffer provider key --connection-uid <uid>``) fetches, so
    the agent always reads exactly the activated connection's key (no wire+active
    mismatch).

    The helper cites the UID rather than the name for the reason this kind has
    no rename route any more: what Coffer writes into another tool's config file
    has to survive the user relabelling the connection, and only the uid does
    (ADR resource-identity-is-an-immutable-uid). 404 when the connection is
    absent, or reaches no agent — disabled, scoped to no agent, or keyless
    (ollama): ``NO_ACTIVE_PROVIDER``, as the wire form answers."""
    return ActiveKeyOut(value=await svc.resolve_connection_key(uid))


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
        actor=actor,
    )
    return _provider_out(resource, await resources.list(kind="agent"))


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


@router.post("/use-builtin/{wire}", response_model=DeactivateOut)
async def use_builtin_provider(
    wire: Protocol,
    svc: ProviderService = Depends(get_provider_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> DeactivateOut:
    """Switch this wire's agent(s) back to their OWN built-in login: remove
    Coffer's projection from the native config and clear the active connection.
    Idempotent — a no-op when the agent already runs built-in."""
    result = await svc.deactivate(wire, actor=actor)
    return DeactivateOut(
        protocol=result.protocol,  # type: ignore[arg-type]
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
