"""/api/v1/memory_stores/* routes (spec 007 redesign).

Domain errors → app-wide handler → ``{error: {code, message, details}}``.
No LLM-provider / 503 path. Actor from ``X-Coffer-Actor``.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Header, Query, Response, status

from coffer.application.memory.scope import GLOBAL_STORE_NAME
from coffer.application.memory.service import MemoryService
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import MemoryStoreNotFound, ResourceNotFound
from coffer.domain.knowledge.document import KIND_MEMORY, WORKSPACE_GLOBAL_PROJECT_ID
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.fact import Actor
from coffer.domain.resource import Resource, ResourceRef
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_memory_service,
    get_resource_service,
)
from coffer.surfaces.http.memory.dependencies import (
    get_project_root_repo,
    get_store_label_repo,
)
from coffer.surfaces.http.memory.organize_state import get_organizer_service
from coffer.surfaces.http.memory.reorg_state import get_reorg_service
from coffer.surfaces.http.memory.schemas import (
    ClearResponse,
    FactCreate,
    FactListOut,
    FactOut,
    FactUpdate,
    MemoryStoreConfigOut,
    MemoryStoreConfigPatch,
    MemoryStoreLabelPatch,
    MemoryStoreListOut,
    MemoryStoreMetrics,
    MemoryStoreOut,
    OrganizeResponse,
    RecallHit,
    RecallRequest,
    RecallResponse,
    ReorgResponse,
    RulesOut,
    Scope,
)

router = APIRouter(
    prefix="/api/v1/memory_stores",
    tags=["memory_stores"],
    dependencies=[Depends(require_token)],
)


def _actor(x_coffer_actor: str | None = Header(default=None)) -> Actor:
    return "agent" if x_coffer_actor == "agent" else "user"


def _scope_of(store_name: str) -> tuple[Scope, str]:
    if store_name == GLOBAL_STORE_NAME:
        return "global", WORKSPACE_GLOBAL_PROJECT_ID
    if store_name.startswith("project-"):
        return "project", store_name[len("project-") :]
    return "project", store_name


def _to_store_out(
    r: Resource, *, store_dir: str, project_root: str | None = None, label: str | None = None
) -> MemoryStoreOut:
    scope, project_id = _scope_of(r.name)
    return MemoryStoreOut(
        ref=str(r.ref),
        kind=r.kind,
        name=r.name,
        scope=scope,
        project_id=project_id,
        project_root=project_root,
        label=label,
        store_dir=store_dir,
        description=r.description,
        config=MemoryStoreConfigOut.from_config(MemoryStoreConfig.model_validate(r.config)),
        enabled=r.enabled,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


async def _store_out(
    r: Resource, roots: object, mem_svc: MemoryService, *, label: str | None = None
) -> MemoryStoreOut:
    scope, _ = _scope_of(r.name)
    project_root = None if scope == "global" else await roots.get(r.name)  # type: ignore[attr-defined]
    try:
        fact_count = await mem_svc.fact_count(store_name=r.name)
    except Exception:
        fact_count = 0
    store_dir = str((await mem_svc.resolved_store(r.name)).store_dir)
    out = _to_store_out(r, store_dir=store_dir, project_root=project_root, label=label)
    out.fact_count = fact_count
    return out


# --- stores -----------------------------------------------------------------


@router.get("", response_model=MemoryStoreListOut)
async def list_stores(
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    labels: object = Depends(get_store_label_repo),
) -> MemoryStoreListOut:
    await mem_svc.ensure_store(GLOBAL_STORE_NAME)
    rs = await svc.list(kind=KIND_MEMORY)
    label_map = await labels.get_many([r.name for r in rs])  # type: ignore[attr-defined]
    return MemoryStoreListOut(
        memory_stores=[await _store_out(r, roots, mem_svc, label=label_map.get(r.name)) for r in rs]
    )


@router.get("/{name}", response_model=MemoryStoreOut)
async def get_store(
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    labels: object = Depends(get_store_label_repo),
) -> MemoryStoreOut:
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    try:
        r = await svc.get(ResourceRef(KIND_MEMORY, name))
    except ResourceNotFound as exc:
        raise MemoryStoreNotFound(name) from exc
    label = await labels.get(name)  # type: ignore[attr-defined]
    return await _store_out(r, roots, mem_svc, label=label)


@router.patch("/{name}", response_model=MemoryStoreOut)
async def update_store(
    name: str,
    body: MemoryStoreConfigPatch,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    labels: object = Depends(get_store_label_repo),
) -> MemoryStoreOut:
    try:
        existing = await svc.get(ResourceRef(KIND_MEMORY, name))
    except ResourceNotFound as exc:
        raise MemoryStoreNotFound(name) from exc
    current = MemoryStoreConfig.model_validate(existing.config)
    patch = body.model_dump(exclude_unset=True)
    validated = MemoryStoreConfig.model_validate(current.model_copy(update=patch).model_dump())
    updated = await svc.update_config(
        ResourceRef(KIND_MEMORY, name),
        new_config=validated.model_dump(mode="json"),
        actor=actor,
    )
    label = await labels.get(name)  # type: ignore[attr-defined]
    return await _store_out(updated, roots, mem_svc, label=label)


@router.patch("/{name}/label", response_model=MemoryStoreOut)
async def update_store_label(
    name: str,
    body: MemoryStoreLabelPatch,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    labels: object = Depends(get_store_label_repo),
) -> MemoryStoreOut:
    """Set or clear a store's display label (007 FR-017c)."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    try:
        r = await svc.get(ResourceRef(KIND_MEMORY, name))
    except ResourceNotFound as exc:
        raise MemoryStoreNotFound(name) from exc
    cleaned = (body.label or "").strip()
    if cleaned:
        await labels.set(name, cleaned)  # type: ignore[attr-defined]
        label: str | None = cleaned
    else:
        await labels.clear(name)  # type: ignore[attr-defined]
        label = None
    return await _store_out(r, roots, mem_svc, label=label)


@router.get("/{name}/metrics", response_model=MemoryStoreMetrics)
async def metrics(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> MemoryStoreMetrics:
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    m = await mem_svc.metrics(store_name=name)
    return MemoryStoreMetrics(
        fact_count=cast(int, m["fact_count"]),
        disk_bytes=cast(int, m["disk_bytes"]),
    )


# --- facts ------------------------------------------------------------------


@router.post(
    "/{name}/facts",
    response_model=FactOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_fact(
    name: str,
    body: FactCreate,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> FactOut:
    scope, _ = _scope_of(name)
    await mem_svc.ensure_store(name)
    fact = await mem_svc.add_fact_to_store(
        store_name=name,
        title=body.title or "",
        description=body.description or "",
        body=body.text,
        actor=actor,
    )
    _, path = await mem_svc.get_fact_with_path(store_name=name, fact_id=fact.id)
    return FactOut.from_fact(fact, store_name=name, scope=scope, path=path)


@router.get("/{name}/facts", response_model=FactListOut)
async def list_facts(
    name: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> FactListOut:
    scope, _ = _scope_of(name)
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    files, total = await mem_svc.list_fact_files(store_name=name, limit=limit, offset=offset)
    out = [
        FactOut.from_fact(ff.fact, store_name=name, scope=scope, path=str(ff.path)) for ff in files
    ]
    return FactListOut(facts=out, total=total)


@router.delete("/{name}/facts", response_model=ClearResponse)
async def clear_facts(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> ClearResponse:
    cleared = await mem_svc.clear(store_name=name, actor=actor)
    return ClearResponse(cleared=cleared)


@router.get("/{name}/facts/{fact_id}", response_model=FactOut)
async def get_fact(
    name: str,
    fact_id: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> FactOut:
    scope, _ = _scope_of(name)
    fact, path = await mem_svc.get_fact_with_path(store_name=name, fact_id=fact_id)
    return FactOut.from_fact(fact, store_name=name, scope=scope, path=path)


@router.patch("/{name}/facts/{fact_id}", response_model=FactOut)
async def update_fact(
    name: str,
    fact_id: str,
    body: FactUpdate,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> FactOut:
    scope, _ = _scope_of(name)
    fact = await mem_svc.update_fact(
        store_name=name,
        fact_id=fact_id,
        new_body=body.text,
        actor=actor,
        new_title=body.title,
        new_description=body.description,
    )
    _, path = await mem_svc.get_fact_with_path(store_name=name, fact_id=fact.id)
    return FactOut.from_fact(fact, store_name=name, scope=scope, path=path)


@router.delete(
    "/{name}/facts/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def forget_fact(
    name: str,
    fact_id: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    await mem_svc.delete_fact(store_name=name, fact_id=fact_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- recall -----------------------------------------------------------------


@router.post("/{name}/recall", response_model=RecallResponse)
async def recall(
    name: str,
    body: RecallRequest,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> RecallResponse:
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    # One query → one answer: the surface never selects a mode; the service
    # resolves it from the store's default_mode (mode stays internal).
    hits, _mode, _fallback = await mem_svc.recall_in_store(
        store_name=name,
        query=body.query,
        top_k=body.top_k,
        mode=None,
        scope=body.scope,
    )
    return RecallResponse(
        hits=[
            RecallHit(id=h.id, text=h.text, score=h.score, source=h.source, time=h.time)
            for h in hits
        ],
    )


# --- organize ---------------------------------------------------------------


@router.post("/{name}/organize", response_model=OrganizeResponse)
async def organize(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    organizer: object = Depends(get_organizer_service),
) -> OrganizeResponse:
    """Drain inbox into topic docs / rules lane (explicit trigger; no auto-fire)."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    result = await organizer.organize(store_name=name)  # type: ignore[attr-defined]
    return OrganizeResponse(
        status=result.status,
        items_processed=result.items_processed,
        topics_created=result.topics_created,
        topics_updated=result.topics_updated,
        rules_appended=result.rules_appended,
        skipped=result.skipped,
        model=result.model,
    )


# --- rules ------------------------------------------------------------------


@router.get("/{name}/rules", response_model=RulesOut)
async def get_rules(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
) -> RulesOut:
    """Return ``rules/rules.md`` text; ``text=None`` when no rules exist yet."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    return RulesOut(text=await mem_svc.get_rules(store_name=name))


# --- reorg ------------------------------------------------------------------


@router.post("/{name}/reorg", response_model=ReorgResponse)
async def reorg(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    reorg_svc: object = Depends(get_reorg_service),
) -> ReorgResponse:
    """Agentic reorg loop over topic docs (explicit trigger; no auto-fire)."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    result = await reorg_svc.reorg(store_name=name)  # type: ignore[attr-defined]
    return ReorgResponse(
        status=result.status,
        topics_before=result.topics_before,
        topics_after=result.topics_after,
        topics_written=result.topics_written,
        topics_superseded=result.topics_superseded,
        model=result.model,
    )
