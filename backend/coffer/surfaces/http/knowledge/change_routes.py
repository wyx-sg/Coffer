"""``/api/v1/knowledge/changes``, a tidy's start and finish, and a collection's
description (spec knowledge "Follow edits across collections in one feed",
"Undo a knowledge delete from its toast", "Record a tidy as one change", "Undo
a tidy", "Name a collection by its folder and edit its description in place").

Every accepted write to a collection is one commit naming its writer. These
routes read that feed back — the web UI reads it only to find the delete a
toast's Undo restores — and put a delete back. A change is named by its
``version`` (its commit id). Without git on the machine the feed answers 503
``KNOWLEDGE_HISTORY_UNAVAILABLE``; writes elsewhere keep working. A
document's versions are read and restored through ``/api/v1/vault`` (spec
vault-storage "Show and restore any version of a vault file or folder").

A collection's description (``PUT /collections/{uid}/description``) is a
person's recorded write like a restore, so it is served by the same service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query

from coffer.application.knowledge.change_service import KnowledgeChangeService
from coffer.application.knowledge.tidy_service import TidyService
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.knowledge.change_schemas import (
    ChangeOut,
    ChangesOut,
    CollectionDescribeIn,
    TidyFinishIn,
    TidyFinishOut,
    TidyStatusOut,
    UndoIn,
    change_out,
    tidy_status_out,
)
from coffer.surfaces.http.knowledge.dependencies import get_change_service, get_tidy_service
from coffer.surfaces.http.knowledge.schemas import CollectionOut, collection_out

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_token)],
)


def _actor(x_coffer_actor: str | None = Header(default=None)) -> str:
    return ACTOR_AGENT if x_coffer_actor == ACTOR_AGENT else ACTOR_USER


@router.get("/changes", response_model=ChangesOut)
async def recent_changes(
    collection: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    svc: KnowledgeChangeService = Depends(get_change_service),  # noqa: B008
) -> ChangesOut:
    """Recent changes across every collection (or one, by its name), newest
    first."""
    page = await svc.changes(collection=collection, limit=limit, cursor=cursor)
    return ChangesOut(
        changes=[change_out(c) for c in page.changes],
        next_cursor=page.next_cursor,
    )


@router.post("/changes/{version}/restore", response_model=ChangeOut)
async def restore_deleted(
    version: str,
    svc: KnowledgeChangeService = Depends(get_change_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ChangeOut:
    """Put back what a delete removed — a document, or a whole collection with
    its documents and README — as one new change naming the user.
    409 ``KNOWLEDGE_RESTORE_CONFLICT`` / ``KNOWLEDGE_COLLECTION_EXISTS`` when
    the path or the name is taken again; nothing is written then."""
    return change_out(await svc.restore_deleted(version, actor=actor))


@router.post("/changes/{version}/undo", response_model=ChangeOut)
async def undo_change(
    version: str,
    body: UndoIn,
    svc: KnowledgeChangeService = Depends(get_change_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> ChangeOut:
    """Put every file a change touched — a tidy — back as it was just before
    it, as one new change naming the user. 409 ``KNOWLEDGE_UNDO_CONFLICT``
    naming the files edited since, unless ``force``; nothing is written then."""
    return change_out(await svc.undo(version, force=body.force, actor=actor))


@router.post("/collections/{uid}/tidy/start", response_model=TidyStatusOut)
async def start_tidy(
    uid: str,
    tidy: TidyService = Depends(get_tidy_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> TidyStatusOut:
    """Open a tidy of the collection: until it finishes, the edits made in it
    are kept for one change ("Record a tidy as one change")."""
    return tidy_status_out(await tidy.start(uid, actor=actor))


@router.post("/collections/{uid}/tidy/finish", response_model=TidyFinishOut)
async def finish_tidy(
    uid: str,
    body: TidyFinishIn,
    tidy: TidyService = Depends(get_tidy_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> TidyFinishOut:
    """Close the collection's tidy and commit what it changed as one change
    carrying the report; ``change`` is ``null`` when it changed nothing."""
    change = await tidy.finish(uid, body.summary, actor=actor)
    return TidyFinishOut(change=change_out(change) if change else None)


@router.put("/collections/{uid}/description", response_model=CollectionOut)
async def describe_collection(
    uid: str,
    body: CollectionDescribeIn,
    svc: KnowledgeChangeService = Depends(get_change_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> CollectionOut:
    """Rewrite the opening paragraph of the collection's README."""
    entry = await svc.describe(uid, body.description, actor=actor)
    return collection_out(entry)
