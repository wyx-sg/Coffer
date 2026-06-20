"""/api/v1/memory_stores/* routes (spec 007 redesign).

Domain errors propagate to the app-wide handler in `surfaces/http/errors.py`,
which renders the standard `{error: {code, message, details}}` envelope. The
memory face has NO LLM-provider / 503 path: writes hand Coffer a clean fact and
``recall`` degrades vector→keyword (flagged) instead of erroring.

Actor comes from ``X-Coffer-Actor`` and is normalised to ``agent``/``user``.
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
    """Derive (scope, project_id) from a store name. ``global`` → the sentinel;
    ``project-<ulid>`` → the project ULID."""
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
    """``_to_store_out`` plus the persisted project root, store dir + fact count.

    ``label`` is the user-set display name (007 FR-017c), resolved by the caller
    so the list endpoint can batch the lookup."""
    scope, _ = _scope_of(r.name)
    project_root = None if scope == "global" else await roots.get(r.name)  # type: ignore[attr-defined]
    try:
        fact_count = cast(int, (await mem_svc.metrics(store_name=r.name)).get("fact_count", 0))
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
    # The global store always exists conceptually — auto-provision it so a fresh
    # install lists it (the per-project stores appear once an agent uses them).
    await mem_svc.ensure_store(GLOBAL_STORE_NAME)
    rs = await svc.list(kind=KIND_MEMORY)
    # One batched lookup for all display labels instead of one query per store.
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
    merged = current.model_copy(update=patch)
    # Re-run validators by round-tripping through the model constructor.
    validated = MemoryStoreConfig.model_validate(merged.model_dump())
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
    """Set or clear a store's display label (007 FR-017c). An empty / whitespace
    body clears it, reverting to the derived (project-dir) or fallback name."""
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
    # ``ensure_store`` provisions well-formed names (``global`` /
    # ``project-<ulid>``) lazily and 404s anything else — an arbitrary POST
    # must never manufacture a store under a mangled name.
    await mem_svc.ensure_store(name)
    fact = await mem_svc.add_fact_to_store(
        store_name=name,
        name=body.name or "",
        description=body.description or "",
        body=body.text,
        actor=actor,
        type=body.type,
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
        new_name=body.name,
        new_description=body.description,
        new_type=body.type,
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
    hits, mode, fallback = await mem_svc.recall_in_store(
        store_name=name,
        query=body.query,
        top_k=body.top_k,
        mode=body.mode,
        scope=body.scope,
    )
    return RecallResponse(
        hits=[
            RecallHit(id=h.id, text=h.text, score=h.score, source=h.source, time=h.time)
            for h in hits
        ],
        mode=mode,
        fallback=fallback,
    )


# --- organize ---------------------------------------------------------------


@router.post("/{name}/organize", response_model=OrganizeResponse)
async def organize(
    name: str,
    mem_svc: MemoryService = Depends(get_memory_service),  # noqa: B008
    organizer: object = Depends(get_organizer_service),
) -> OrganizeResponse:
    """Drain the store's ``knowledge/inbox/`` into coherent topic documents via
    Coffer's internal LLM (explicit trigger; no auto-fire). ``no_model`` /
    ``empty`` are clean no-ops, not errors."""
    if name == GLOBAL_STORE_NAME:
        await mem_svc.ensure_store(name)
    result = await organizer.organize(store_name=name)  # type: ignore[attr-defined]
    return OrganizeResponse(
        status=result.status,
        items_processed=result.items_processed,
        topics_created=result.topics_created,
        topics_updated=result.topics_updated,
        skipped=result.skipped,
        model=result.model,
    )
