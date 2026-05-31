"""/api/v1/memory_stores/* routes.

Domain errors propagate to the app-wide handler in `surfaces/http/errors.py`,
which renders the standard `{error: {code, message, details}}` envelope.
Routes only translate when they need a kind-specific code.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response, status

from coffer.application.memory.service import MemoryService
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import MemoryStoreNotFound, ResourceNotFound
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.record import Actor, MemoryRecord
from coffer.domain.resource import Resource, ResourceRef
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_memory_service, get_resource_service
from coffer.surfaces.http.memory.schemas import (
    MemoryClearResponse,
    MemoryCreate,
    MemoryListOut,
    MemoryOut,
    MemorySearchHit,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStoreCreateRequest,
    MemoryStoreListOut,
    MemoryStoreMetricsOut,
    MemoryStoreOut,
    MemoryUpdate,
)

router = APIRouter(
    prefix="/api/v1/memory_stores",
    tags=["memory_stores"],
    dependencies=[Depends(require_token)],
)


def _actor(x_coffer_actor: str | None = Header(default=None)) -> Actor:
    val = x_coffer_actor or "api"
    if val == "agent":
        return "agent"
    return "user"


def _to_store_out(r: Resource) -> MemoryStoreOut:
    return MemoryStoreOut(
        ref=str(r.ref),
        kind=r.kind,
        name=r.name,
        description=r.description,
        config=MemoryStoreConfig.model_validate(r.config),
        enabled=r.enabled,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _to_memory_out(m: MemoryRecord) -> MemoryOut:
    return MemoryOut(
        id=m.id,
        store_name=m.store_name,
        text=m.text,
        actor=m.actor,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@router.get("", response_model=MemoryStoreListOut)
async def list_stores(
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> MemoryStoreListOut:
    rs = await svc.list(kind="memory")
    return MemoryStoreListOut(memory_stores=[_to_store_out(r) for r in rs])


@router.post(
    "",
    response_model=MemoryStoreOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_store(
    body: MemoryStoreCreateRequest,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> MemoryStoreOut:
    created = await svc.register(
        kind="memory",
        name=body.name,
        config=body.config.model_dump(),
        actor=actor,
        description=body.description,
    )
    return _to_store_out(created)


@router.get("/{name}", response_model=MemoryStoreOut)
async def get_store(
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> MemoryStoreOut:
    try:
        r = await svc.get(ResourceRef("memory", name))
    except ResourceNotFound as exc:
        raise MemoryStoreNotFound(name) from exc
    return _to_store_out(r)


@router.get("/{name}/metrics", response_model=MemoryStoreMetricsOut)
async def metrics(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> MemoryStoreMetricsOut:
    count, disk = await mem_svc.metrics(store_name=name)
    return MemoryStoreMetricsOut(memory_count=count, disk_bytes=disk)


@router.post(
    "/{name}/memories",
    response_model=MemoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_memory(
    name: str,
    body: MemoryCreate,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> MemoryOut:
    m = await mem_svc.add(store_name=name, text=body.text, actor=actor)
    return _to_memory_out(m)


@router.get("/{name}/memories", response_model=MemoryListOut)
async def list_memories(
    name: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> MemoryListOut:
    rows, total = await mem_svc.list_memories(store_name=name, limit=limit, offset=offset)
    return MemoryListOut(memories=[_to_memory_out(m) for m in rows], total=total)


@router.get("/{name}/memories/{memory_id}", response_model=MemoryOut)
async def get_memory(
    name: str,
    memory_id: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> MemoryOut:
    m = await mem_svc.get(store_name=name, memory_id=memory_id)
    return _to_memory_out(m)


@router.patch("/{name}/memories/{memory_id}", response_model=MemoryOut)
async def update_memory(
    name: str,
    memory_id: str,
    body: MemoryUpdate,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> MemoryOut:
    m = await mem_svc.update(
        store_name=name,
        memory_id=memory_id,
        new_text=body.text,
        actor=actor,
    )
    return _to_memory_out(m)


@router.delete(
    "/{name}/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_memory(
    name: str,
    memory_id: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    await mem_svc.delete(store_name=name, memory_id=memory_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{name}/memories/clear", response_model=MemoryClearResponse)
async def clear_memories(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> MemoryClearResponse:
    cleared = await mem_svc.clear(store_name=name, actor=actor)
    return MemoryClearResponse(cleared=cleared)


@router.post("/{name}/search", response_model=MemorySearchResponse)
async def search_memory(
    name: str,
    body: MemorySearchRequest,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> MemorySearchResponse:
    hits = await mem_svc.search(store_name=name, query=body.query, top_k=body.top_k)
    return MemorySearchResponse(
        hits=[
            MemorySearchHit(id=h.id, text=h.text, score=h.score, created_at=h.created_at)
            for h in hits
        ]
    )
