"""/api/v1/resources/* — kind-agnostic Resource CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Resource
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
        uid=r.uid,
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
    name: str | None = Query(
        default=None,
        description=(
            "Filter by exact label. This is the ONE place a name may be used to "
            "find a resource: it is how a surface that started from what a human "
            "typed — the CLI — turns that into the uid every other route takes."
        ),
    ),
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceListOut:
    rs = await svc.list(kind=kind)
    if name is not None:
        rs = [r for r in rs if r.name == name]
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


@router.get("/{uid}", response_model=ResourceOut)
async def get_resource(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceOut:
    return _to_out(await svc.get(uid))


@router.patch("/{uid}", response_model=ResourceOut)
async def update_resource(
    uid: str,
    body: ResourceUpdate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    """Edit a resource's label, description or config.

    ``name`` is an ordinary field here, at the same level as ``description``,
    which is the whole user-facing point of the identity change: while the name
    WAS the identity, moving it needed its own route, and only one kind of the
    seven ever got one.

    The rename runs first and on its own, because it is the one part that can
    be refused for a reason the config half knows nothing about — a label
    another resource of this kind already holds (409).
    """
    r = await svc.get(uid)
    if body.name is not None:
        r = await svc.rename(uid, body.name, actor=actor)
    # ``model_fields_set``, not a value comparison. Every field here is
    # optional and ``None`` is a legal VALUE for ``description``, so "the
    # client did not mention it" and "the client asked to clear it" are the
    # same ``None`` and can only be told apart by which keys the body carried.
    # Comparing values instead read a rename-only PATCH as a request to clear
    # the description, and wiped it — silently, with a spurious update event in
    # the audit trail to match.
    sent = body.model_fields_set
    if "config" in sent or "description" in sent:
        r = await svc.update_config(
            uid,
            # An explicit ``"config": null`` leaves the config alone rather
            # than clearing it: a resource without a config is not a state any
            # kind has, so there is nothing for null to mean here.
            new_config=body.config if body.config is not None else r.config,
            actor=actor,
            description=body.description if "description" in sent else r.description,
        )
    return _to_out(r)


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_resource(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.delete(uid, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{uid}/enable", response_model=ResourceOut)
async def enable_resource(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    return _to_out(await svc.set_enabled(uid, enabled=True, actor=actor))


@router.post("/{uid}/disable", response_model=ResourceOut)
async def disable_resource(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    return _to_out(await svc.set_enabled(uid, enabled=False, actor=actor))


@router.get("/{uid}/scope", response_model=ResourceScopeOut)
async def get_resource_scope(
    uid: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> ResourceScopeOut:
    r = await svc.get(uid)
    return ResourceScopeOut(scope=ScopeOut.of(r.scope), supports_scope=svc.supports_scope(r.kind))


@router.put("/{uid}/scope", response_model=ResourceOut)
async def update_resource_scope(
    uid: str,
    body: ResourceScopeUpdate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ResourceOut:
    # Deliberately NOT gated on allow_lifecycle_kind — scope is a
    # framework-level concern orthogonal to a kind's creation invariants
    # (ResourceService.update_scope, ADR: per-agent-resource-scope).
    scope = body.scope.to_domain() if body.scope is not None else None
    return _to_out(await svc.update_scope(uid, scope, actor=actor))
