"""``/api/v1/knowledge/{scope}/entries*`` — the entries an agent or person wrote.

Registered on the shared ``knowledge`` router (imported from ``routes``) so a
scope's entries and its ingested documents live under one path tree. Split out
only to keep each module under the project's file-size ceiling.

Entries are per-item markdown files under the scope's ``knowledge/`` lane. No
LLM at write time: a write is a file plus an index row plus an audit event.
"""

from __future__ import annotations

from fastapi import Depends, Query, Response, status

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.entry import Actor
from coffer.domain.knowledge.scope import KnowledgeScope, scope_kind_of
from coffer.surfaces.http.dependencies import get_knowledge_service
from coffer.surfaces.http.knowledge.routes import _actor, _ensure_auto, _scope_kind, router
from coffer.surfaces.http.knowledge.schemas import (
    ClearResponse,
    EntryCreate,
    EntryListOut,
    EntryOut,
    EntryUpdate,
)


@router.post("/{name}/entries", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
async def add_entry(
    name: str,
    body: EntryCreate,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> EntryOut:
    if scope_kind_of(name) is not KnowledgeScope.NAMED:
        await k_svc.ensure_scope(name)
    entry = await k_svc.add_fact_to_scope(
        scope_name=name,
        title=body.title or "",
        description=body.description or "",
        body=body.text,
        actor=actor,
    )
    _, path = await k_svc.get_fact_with_path(scope_name=name, fact_id=entry.id)
    return EntryOut.from_entry(entry, scope_name=name, scope=_scope_kind(name), path=path)


@router.get("/{name}/entries", response_model=EntryListOut)
async def list_entries(
    name: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> EntryListOut:
    await _ensure_auto(k_svc, name)
    files, total = await k_svc.list_fact_files(scope_name=name, limit=limit, offset=offset)
    kind = _scope_kind(name)
    return EntryListOut(
        entries=[
            EntryOut.from_entry(ff.fact, scope_name=name, scope=kind, path=str(ff.path))
            for ff in files
        ],
        total=total,
    )


@router.delete("/{name}/entries", response_model=ClearResponse)
async def clear_entries(
    name: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> ClearResponse:
    """Remove every entry in a scope; the scope itself survives."""
    return ClearResponse(cleared=await k_svc.clear(scope_name=name, actor=actor))


@router.get("/{name}/entries/{entry_id}", response_model=EntryOut)
async def get_entry(
    name: str,
    entry_id: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> EntryOut:
    entry, path = await k_svc.get_fact_with_path(scope_name=name, fact_id=entry_id)
    return EntryOut.from_entry(entry, scope_name=name, scope=_scope_kind(name), path=path)


@router.patch("/{name}/entries/{entry_id}", response_model=EntryOut)
async def update_entry(
    name: str,
    entry_id: str,
    body: EntryUpdate,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> EntryOut:
    entry = await k_svc.update_fact(
        scope_name=name,
        fact_id=entry_id,
        new_body=body.text,
        actor=actor,
        new_title=body.title,
        new_description=body.description,
    )
    _, path = await k_svc.get_fact_with_path(scope_name=name, fact_id=entry.id)
    return EntryOut.from_entry(entry, scope_name=name, scope=_scope_kind(name), path=path)


@router.delete(
    "/{name}/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_entry(
    name: str,
    entry_id: str,
    k_svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> Response:
    await k_svc.delete_fact(scope_name=name, fact_id=entry_id, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
