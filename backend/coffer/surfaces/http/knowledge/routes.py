"""``/api/v1/knowledge/*`` — the human's side of the knowledge directory.

Six routes for six gestures: create a collection, list them, walk one level of
the catalogue, read a file, write one, delete one — plus a manual tidy trigger.
There is no upload, reindex, check-sources, embedding or settings route,
because none of those exist any more (spec knowledge FR-060). Deleting a
collection goes through the kind-agnostic Resource route, since collection
lifecycle is a Resource concern.

These routes are the *user's* surface and therefore unscoped: per-agent
authorization (FR-012) governs what an agent sees through the MCP tools, not
what the person who owns the vault sees in their own UI.

Domain errors propagate to the app-wide handler in ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response, status

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER
from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_knowledge_service
from coffer.surfaces.http.knowledge.schemas import (
    CollectionCreate,
    CollectionListOut,
    CollectionOut,
    DirectoryOut,
    FileOut,
    FileSummaryOut,
    FileWrite,
    GrepMatchOut,
    GrepOut,
    TidyOut,
    TreeOut,
)
from coffer.surfaces.http.knowledge.tidy_state import get_tidy_runner

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_token)],
)


def _actor_kind(x_coffer_actor: str | None = Header(default=None)) -> str:
    return ACTOR_AGENT if x_coffer_actor == ACTOR_AGENT else ACTOR_USER


def _file_out(file: object) -> FileOut:
    return FileOut.model_validate(file, from_attributes=True)


@router.get("/collections", response_model=CollectionListOut)
async def list_collections(
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> CollectionListOut:
    found = await svc.list_collections()
    return CollectionListOut(
        collections=[CollectionOut.model_validate(c, from_attributes=True) for c in found]
    )


@router.post("/collections", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
async def create_collection(
    body: CollectionCreate,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> CollectionOut:
    created = await svc.create_collection(body.name, actor=actor, description=body.description)
    return CollectionOut.model_validate(created, from_attributes=True)


@router.get("/tree", response_model=TreeOut)
async def read_tree(
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> TreeOut:
    level = await svc.list_level(path)
    return TreeOut(
        path=level.path,
        directories=[
            DirectoryOut.model_validate(d, from_attributes=True) for d in level.directories
        ],
        files=[FileSummaryOut.model_validate(f, from_attributes=True) for f in level.files],
    )


@router.get("/file", response_model=FileOut)
async def read_file(
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> FileOut:
    return _file_out(await svc.read(path))


@router.put("/file", response_model=FileOut)
async def write_file(
    body: FileWrite,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> FileOut:
    if (body.path is None) == (body.directory is None):
        raise UnsafeKnowledgePath(
            body.path or body.directory or "",
            "a write names exactly one of 'path' or 'directory'",
        )
    written = await svc.write(
        title=body.title,
        description=body.description,
        body=body.body,
        directory=body.directory,
        relpath=body.path,
        actor_kind=actor,
        actor=actor,
    )
    return _file_out(written)


@router.delete("/file", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_file(
    path: str = Query(min_length=1),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> Response:
    await svc.delete(path, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/grep", response_model=GrepOut)
async def grep(
    pattern: str = Query(min_length=1),
    collection: str | None = Query(default=None),
    max_matches: int = Query(default=200, ge=1, le=500),
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
) -> GrepOut:
    outcome = await svc.grep(pattern, collection=collection, max_matches=max_matches)
    return GrepOut(
        matches=[GrepMatchOut.model_validate(m, from_attributes=True) for m in outcome.matches],
        truncated=outcome.truncated,
    )


@router.post("/collections/{name}/tidy", response_model=TidyOut)
async def tidy(
    name: str,
    svc: KnowledgeService = Depends(get_knowledge_service),  # noqa: B008
    actor: str = Depends(_actor_kind),
) -> TidyOut:
    result = await get_tidy_runner()(svc, name, actor=actor)
    return TidyOut(**{"collection": name, **result})
