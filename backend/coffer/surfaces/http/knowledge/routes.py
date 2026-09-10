"""``/api/v1/knowledge/*`` — scope + entry routes for the one knowledge kind.

The two former route trees (``/memory_stores/*`` and ``/knowledge_bases/*``)
collapse into this one, with the scope name as the path segment. A scope is a
scope: ``global`` and ``project-<ULID>`` auto-provision on first use, a named
collection is created deliberately through ``POST /api/v1/knowledge``.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``
→ ``{error: {code, message, details}}``. Actor from ``X-Coffer-Actor``.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Header, status

from coffer.application.knowledge.service import KnowledgeService
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import MemoryStoreNotFound, ResourceNotFound
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.domain.knowledge.entry import Actor
from coffer.domain.knowledge.retrieval import RetrievalMode
from coffer.domain.knowledge.scope import GLOBAL_SCOPE_NAME, scope_kind_of
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import Resource, ResourceRef
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_knowledge_service,
    get_resource_service,
)
from coffer.surfaces.http.knowledge.dependencies import (
    get_project_root_repo,
    get_scope_label_repo,
)
from coffer.surfaces.http.knowledge.reorg_state import get_reorg_service
from coffer.surfaces.http.knowledge.schemas import (
    KnowledgeConfigPatch,
    OrganizeResponse,
    RecallHit,
    RecallRequest,
    RecallResponse,
    ScopeCreate,
    ScopeKind,
    ScopeLabelPatch,
    ScopeListOut,
    ScopeMetrics,
    ScopeOut,
)

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_token)],
)


def _actor(x_coffer_actor: str | None = Header(default=None)) -> Actor:
    return "agent" if x_coffer_actor == "agent" else "user"


def _scope_kind(scope_name: str) -> ScopeKind:
    """The wire ``scope`` discriminator, derived from the name."""
    return scope_kind_of(scope_name).value


async def _ensure_auto(svc: KnowledgeService, name: str) -> None:
    """Provision ``global`` on first access; other names must already exist."""
    if name == GLOBAL_SCOPE_NAME:
        await svc.ensure_scope(name)


async def _scope_out(
    r: Resource, roots: object, svc: KnowledgeService, *, label: str | None = None
) -> ScopeOut:
    kind = _scope_kind(r.name)
    project_root = await roots.get(r.name) if kind == "project" else None  # type: ignore[attr-defined]
    try:
        entry_count = await svc.fact_count(scope_name=r.name)
    except Exception:
        entry_count = 0
    try:
        # Cheap indexed count only: the list output discards disk_bytes, so we
        # skip ``metrics()``' per-scope ``du_bytes`` disk walk.
        document_count = await svc.document_count(scope_name=r.name)
    except Exception:
        document_count = 0
    resolved = await svc.resolved_scope(r.name)
    return ScopeOut(
        ref=str(r.ref),
        kind=r.kind,
        name=r.name,
        scope=kind,
        project_id=resolved.project_id,
        project_root=project_root,
        label=label,
        scope_dir=str(resolved.store_dir),
        description=r.description,
        config=KnowledgeConfig.model_validate(r.config),
        enabled=r.enabled,
        entry_count=entry_count,
        document_count=document_count,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


async def _require_resource(svc: ResourceService, name: str) -> Resource:
    try:
        return await svc.get(ResourceRef(KIND_KNOWLEDGE, name))
    except ResourceNotFound as exc:
        raise MemoryStoreNotFound(name) from exc


# --- scopes -----------------------------------------------------------------


@router.get("", response_model=ScopeListOut)
async def list_scopes(
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    labels: object = Depends(get_scope_label_repo),
) -> ScopeListOut:
    """Every knowledge scope: the two auto-scopes plus named collections."""
    await k_svc.ensure_scope(GLOBAL_SCOPE_NAME)
    rs = await svc.list(kind=KIND_KNOWLEDGE)
    label_map = await labels.get_many([r.name for r in rs])  # type: ignore[attr-defined]
    return ScopeListOut(
        scopes=[await _scope_out(r, roots, k_svc, label=label_map.get(r.name)) for r in rs]
    )


@router.post("", response_model=ScopeOut, status_code=status.HTTP_201_CREATED)
async def create_scope(
    body: ScopeCreate,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    actor: Actor = Depends(_actor),  # noqa: B008
) -> ScopeOut:
    """Create a named collection. The auto-scopes are rejected by the schema."""
    created = await svc.register(
        kind=KIND_KNOWLEDGE,
        name=body.name,
        config=body.config.model_dump(mode="json"),
        actor=actor,
        description=body.description,
    )
    return await _scope_out(created, roots, k_svc)


@router.get("/{name}", response_model=ScopeOut)
async def get_scope(
    name: str,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    labels: object = Depends(get_scope_label_repo),
) -> ScopeOut:
    await _ensure_auto(k_svc, name)
    r = await _require_resource(svc, name)
    label = await labels.get(name)  # type: ignore[attr-defined]
    return await _scope_out(r, roots, k_svc, label=label)


@router.patch("/{name}", response_model=ScopeOut)
async def update_scope(
    name: str,
    body: KnowledgeConfigPatch,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    labels: object = Depends(get_scope_label_repo),
) -> ScopeOut:
    """Patch a scope's config. Changing a retrieval or chunking field re-indexes
    it (the kind's ``on_update_config`` hook); the files stay the truth."""
    existing = await _require_resource(svc, name)
    current = KnowledgeConfig.model_validate(existing.config)
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    validated = KnowledgeConfig.model_validate(current.model_copy(update=patch).model_dump())
    updated = await svc.update_config(
        ResourceRef(KIND_KNOWLEDGE, name),
        new_config=validated.model_dump(mode="json"),
        actor=actor,
    )
    label = await labels.get(name)  # type: ignore[attr-defined]
    return await _scope_out(updated, roots, k_svc, label=label)


@router.patch("/{name}/label", response_model=ScopeOut)
async def update_scope_label(
    name: str,
    body: ScopeLabelPatch,
    svc: ResourceService = Depends(get_resource_service),  # noqa: B008
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    roots: object = Depends(get_project_root_repo),
    labels: object = Depends(get_scope_label_repo),
) -> ScopeOut:
    """Set or clear a scope's display label."""
    await _ensure_auto(k_svc, name)
    r = await _require_resource(svc, name)
    cleaned = (body.label or "").strip()
    if cleaned:
        await labels.set(name, cleaned)  # type: ignore[attr-defined]
        label: str | None = cleaned
    else:
        await labels.clear(name)  # type: ignore[attr-defined]
        label = None
    return await _scope_out(r, roots, k_svc, label=label)


@router.get("/{name}/metrics", response_model=ScopeMetrics)
async def metrics(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> ScopeMetrics:
    """The union of both faces' numbers for one scope."""
    await _ensure_auto(k_svc, name)
    m = await k_svc.metrics(scope_name=name)
    return ScopeMetrics(
        entry_count=cast(int, m["fact_count"]),
        document_count=cast(int, m["document_count"]),
        chunk_count=cast(int, m["chunk_count"]),
        documents_degraded=cast(int, m["documents_degraded"]),
        indexed_modes=cast("list[RetrievalMode]", m["enabled_modes"]),
        disk_bytes=cast(int, m["disk_bytes"]),
    )


# --- recall -----------------------------------------------------------------


@router.post("/{name}/recall", response_model=RecallResponse)
async def recall(
    name: str,
    body: RecallRequest,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> RecallResponse:
    """Recall entries from a scope (one query → one answer).

    The surface never selects a retrieval mode; the service resolves it from the
    scope's ``default_mode`` and degrades vector→keyword rather than erroring."""
    await _ensure_auto(k_svc, name)
    hits, _mode, _fallback = await k_svc.recall_in_scope(
        scope_name=name,
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


# --- the tidy pass ----------------------------------------------------------


@router.post("/{name}/organize", response_model=OrganizeResponse)
async def organize(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    tidy: object = Depends(get_reorg_service),
) -> OrganizeResponse:
    """Tidy a scope's notes now, instead of waiting for the background trigger.

    There is one pass and one name for it. The same service runs on idle after a
    write and on the periodic sweep; this endpoint only says "now", so a person
    watching the page never has to wonder which of two buttons reshapes what
    they wrote."""
    await _ensure_auto(k_svc, name)
    result = await tidy.reorg(scope_name=name)  # type: ignore[attr-defined]
    return OrganizeResponse(
        status=result.status,
        notes_before=result.notes_before,
        notes_after=result.notes_after,
        notes_written=result.notes_written,
        notes_archived=result.notes_archived,
        model=result.model,
    )
