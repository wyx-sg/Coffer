"""/api/v1/resources/* — kind-agnostic Resource CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Resource, ResourceRef
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_resource_service
from coffer.surfaces.http.schemas import (
    ResourceCreate,
    ResourceListOut,
    ResourceOut,
    ResourceScopeOut,
    ResourceScopeUpdate,
    ResourceUpdate,
    ScopeOut,
)

router = APIRouter(
    prefix="/api/v1/resources",
    tags=["resources"],
    dependencies=[Depends(require_token)],
)


def _to_out(r: Resource) -> ResourceOut:
    return ResourceOut(
        ref=str(r.ref),
        kind=r.kind,
        name=r.name,
        description=r.description,
        config=r.config,
        scope=ScopeOut.of(r.scope),
        enabled=r.enabled,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


_actor = get_actor


@router.get("", response_model=ResourceListOut)
async def list_resources(
    kind: str | None = Query(default=None),
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceListOut:
    rs = await svc.list(kind=kind)
    return ResourceListOut(resources=[_to_out(r) for r in rs])


@router.post(
    "",
    response_model=ResourceOut,
    status_code=status.HTTP_201_CREATED,
)
async def register_resource(
    body: ResourceCreate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    r = await svc.register(
        kind=body.kind,
        name=body.name,
        config=body.config,
        description=body.description,
        actor=actor,
    )
    return _to_out(r)


@router.get("/{kind}/{name}", response_model=ResourceOut)
async def get_resource(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceOut:
    r = await svc.get(ResourceRef(kind, name))
    return _to_out(r)


@router.patch("/{kind}/{name}", response_model=ResourceOut)
async def update_resource(
    kind: str,
    name: str,
    body: ResourceUpdate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    # An ABSENT field leaves what is stored alone. The service takes a WHOLE
    # resource, so anything this route does not carry forward it writes a null
    # over — which a PATCH that can now say only `{"name": ...}` would turn
    # into a silent erasure of the description beside it.
    #
    # An explicit null is "leave it alone" too, and not "make it empty". The
    # config is a document a kind's own schema owns; a client that wanted it
    # emptied would say `{}`, and one that said null is a client that filled in
    # a field it had no value for.
    sent = body.model_fields_set
    edits_config = "config" in sent and body.config is not None
    edits_description = "description" in sent

    # A rename ALONE touches no config, so it runs no config write. Rewriting
    # the stored config back over itself is not a no-op: it re-validates, it
    # re-probes every credential the config cites, it fires the kind's update
    # hook and it records a `resource_updated` with identical before and after.
    # A rename refused because a credential this resource mentions has since
    # been deleted is a refusal about something the caller did not touch.
    if edits_config or edits_description:
        existing = await svc.get(ResourceRef(kind, name))
        r = await svc.update_config(
            ResourceRef(kind, name),
            new_config=body.config if body.config is not None else existing.config,
            actor=actor,
            description=body.description if edits_description else existing.description,
        )
    else:
        r = await svc.get(ResourceRef(kind, name))
    # The rename comes LAST, so a refused config leaves the name alone: one
    # PATCH that renamed a resource and then rejected its config would have
    # moved the thing the caller was about to retry against.
    if body.name is not None:
        r = await svc.rename(ResourceRef(kind, name), body.name, actor=actor)
    return _to_out(r)


@router.delete("/{kind}/{name}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_resource(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.delete(ResourceRef(kind, name), actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{kind}/{name}/enable", response_model=ResourceOut)
async def enable_resource(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    r = await svc.set_enabled(ResourceRef(kind, name), enabled=True, actor=actor)
    return _to_out(r)


@router.post("/{kind}/{name}/disable", response_model=ResourceOut)
async def disable_resource(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    r = await svc.set_enabled(ResourceRef(kind, name), enabled=False, actor=actor)
    return _to_out(r)


@router.get("/{kind}/{name}/scope", response_model=ResourceScopeOut)
async def get_resource_scope(
    kind: str,
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceScopeOut:
    r = await svc.get(ResourceRef(kind, name))
    return ResourceScopeOut(scope=ScopeOut.of(r.scope), supports_scope=svc.supports_scope(r.kind))


@router.put("/{kind}/{name}/scope", response_model=ResourceOut)
async def update_resource_scope(
    kind: str,
    name: str,
    body: ResourceScopeUpdate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    # Deliberately NOT gated on allow_lifecycle_kind — scope is a
    # framework-level concern orthogonal to a kind's creation invariants
    # (ResourceService.update_scope, ADR: per-agent-resource-scope).
    scope = body.scope.to_domain() if body.scope is not None else None
    r = await svc.update_scope(ResourceRef(kind, name), scope, actor=actor)
    return _to_out(r)
