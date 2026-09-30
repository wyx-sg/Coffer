"""``/api/v1/knowledge/history`` and ``/api/v1/knowledge/changes`` — a
collection's history (spec knowledge "Keep every document's history and undo a
pass as a whole", "Follow knowledge changes across collections", "Restore a
deleted collection or document from Recent changes").

Also a collection's description (``PUT /collections/{uid}/description``): a
person's recorded write like a restore, so it is served by the same service.

Every accepted write to a collection is one commit naming its writer; these
routes read that history back, restore one version of a document, and undo a
curation pass as a whole. Documents are addressed by their knowledge-root-
relative path, as on the file routes, and a change by its ``version`` (its
commit id). Without git on the machine every route here answers 503
``KNOWLEDGE_HISTORY_UNAVAILABLE``; writes elsewhere keep working.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query

from coffer.application.knowledge.history_service import KnowledgeHistoryService
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.knowledge.dependencies import get_history_service
from coffer.surfaces.http.knowledge.history_schemas import (
    ChangeDetailOut,
    ChangeOut,
    ChangesOut,
    CollectionDescribeIn,
    DocumentHistoryOut,
    VersionBodyOut,
    VersionDiffOut,
    VersionRestoreIn,
    change_out,
    detail_out,
    history_out,
    waiting_out,
)
from coffer.surfaces.http.knowledge.schemas import CollectionOut, FileOut

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_token)],
)


def _actor(x_coffer_actor: str | None = Header(default=None)) -> str:
    return ACTOR_AGENT if x_coffer_actor == ACTOR_AGENT else ACTOR_USER


@router.get("/history", response_model=DocumentHistoryOut)
async def document_history(
    path: str = Query(min_length=1),
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
) -> DocumentHistoryOut:
    """A document's versions, newest first, each with its writer and time."""
    return history_out(path, await svc.versions(path))


@router.get("/history/diff", response_model=VersionDiffOut)
async def version_diff(
    path: str = Query(min_length=1),
    version: str = Query(min_length=4),
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
) -> VersionDiffOut:
    """What one version did to the document."""
    diff = await svc.version_diff(path, version)
    return VersionDiffOut(
        version=version,
        path=diff.path,
        status=diff.status,  # type: ignore[arg-type]
        diff=diff.diff,
        added=diff.added,
        removed=diff.removed,
    )


@router.get("/history/version", response_model=VersionBodyOut)
async def version_body(
    path: str = Query(min_length=1),
    version: str = Query(min_length=4),
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
) -> VersionBodyOut:
    """The document's body as one version left it."""
    body = await svc.version_body(path, version)
    return VersionBodyOut(path=path, version=version, body=body)


@router.post("/history/restore", response_model=FileOut)
async def restore_version(
    body: VersionRestoreIn,
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> FileOut:
    """Put one version of a document back, as a new change naming the user."""
    restored = await svc.restore(body.path, body.version, actor=actor)
    return FileOut.model_validate(restored, from_attributes=True)


@router.get("/changes", response_model=ChangesOut)
async def recent_changes(
    collection: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
) -> ChangesOut:
    """Recent changes across every collection (or one, by its name), newest
    first, with the items still waiting in each inbox."""
    page = await svc.changes(collection=collection, limit=limit, cursor=cursor)
    return ChangesOut(
        changes=[change_out(c) for c in page.changes],
        waiting=[waiting_out(w) for w in page.waiting],
        next_cursor=page.next_cursor,
    )


@router.get("/changes/{version}", response_model=ChangeDetailOut)
async def change_detail(
    version: str,
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
) -> ChangeDetailOut:
    """One change in full: every document it touched, with its diff."""
    return detail_out(await svc.change(version))


@router.post("/changes/{version}/undo", response_model=ChangeOut)
async def undo_pass(
    version: str,
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ChangeOut:
    """Undo a curation pass as a whole. 409 ``KNOWLEDGE_UNDO_CONFLICT`` names
    the document a later change would lose; nothing is written then."""
    return change_out(await svc.undo(version, actor=actor))


@router.post("/changes/{version}/restore", response_model=ChangeOut)
async def restore_deleted(
    version: str,
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ChangeOut:
    """Put back what a delete removed — a document, or a whole collection with
    its documents, README and waiting items — as one new change naming the user.
    409 ``KNOWLEDGE_RESTORE_CONFLICT`` / ``KNOWLEDGE_COLLECTION_EXISTS`` when
    the path or the name is taken again; nothing is written then."""
    return change_out(await svc.restore_deleted(version, actor=actor))


@router.put("/collections/{uid}/description", response_model=CollectionOut)
async def describe_collection(
    uid: str,
    body: CollectionDescribeIn,
    svc: KnowledgeHistoryService = Depends(get_history_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> CollectionOut:
    """Rewrite the opening paragraph of the collection's README."""
    entry = await svc.describe(uid, body.description, actor=actor)
    return CollectionOut.model_validate(entry, from_attributes=True)
