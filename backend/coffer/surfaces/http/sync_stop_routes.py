"""/api/v1/sync — what a round waiting for a person needs
(spec vault-sync "Report a join before applying it", "Hold a round that would
lose too much", "Snapshot before applying and roll back from it").

A stop is answered file by file — keep this machine's, take the other's, or
edit a marked-up copy — and nothing is written into the vault until
``/continue``. A hold is confirmed or restored, and either answer continues
the round. Paths are vault-relative and travel in the body or a query.
"""

from __future__ import annotations

from fastapi import Query

from coffer.application.sync.round_answers import SyncNothingStopped
from coffer.domain.sync.stops import Answer
from coffer.surfaces.http.sync_dependencies import get_sync_service, router
from coffer.surfaces.http.sync_projections import (
    change_out,
    conflict_out,
    preview_out,
    round_out,
    stopped_out,
)
from coffer.surfaces.http.sync_schemas import RoundOut
from coffer.surfaces.http.sync_stop_schemas import (
    EditorCopyOut,
    FileAnswerIn,
    FilePathIn,
    FileVersionsOut,
    JoinChoicesIn,
    JoinChoicesOut,
    JoinPreviewOut,
    RollbackPlanOut,
    StopStateOut,
)

_ACTOR = "user"


# --- joining ------------------------------------------------------------------------


@router.get("/join/preview", response_model=JoinPreviewOut)
async def join_preview() -> JoinPreviewOut:
    """What joining the remote would do; nothing is applied."""
    return preview_out(await get_sync_service().join_preview())


@router.post("/join", response_model=RoundOut)
async def join() -> RoundOut:
    """Join as the preview said: nothing is deleted on either side."""
    return round_out(await get_sync_service().join())


@router.get("/join-choices", response_model=JoinChoicesOut)
async def join_choices() -> JoinChoicesOut:
    files = await get_sync_service().join_choices()
    return JoinChoicesOut(files=[conflict_out(c) for c in files])


@router.post("/join-choices", response_model=JoinChoicesOut)
async def choose(body: JoinChoicesIn) -> JoinChoicesOut:
    """Keep this machine's version (pushed by the next round) or take the
    remote's, for one or several of a join's differing files."""
    remaining = await get_sync_service().choose(
        [(c.path, Answer(c.answer)) for c in body.choices], actor=_ACTOR
    )
    return JoinChoicesOut(files=[conflict_out(c) for c in remaining])


# --- a stopped round ----------------------------------------------------------------------


async def _stop_state() -> StopStateOut:
    found = await get_sync_service().stopped()
    return StopStateOut(stopped=found is not None, round=stopped_out(found) if found else None)


@router.get("/stop", response_model=StopStateOut)
async def stop() -> StopStateOut:
    return await _stop_state()


@router.post("/stop/files/answer", response_model=StopStateOut)
async def answer(body: FileAnswerIn) -> StopStateOut:
    """Record an answer for one file; ``edited`` reads the saved editor copy
    and refuses it while a conflict marker is left in it."""
    await get_sync_service().answer(body.path, body.answer)
    return await _stop_state()


@router.post("/stop/files/editor", response_model=EditorCopyOut)
async def open_editor(body: FilePathIn) -> EditorCopyOut:
    """Write (once) git's marked-up merge of the file outside the vault and
    answer where it is."""
    where = await get_sync_service().open_editor(body.path)
    return EditorCopyOut(path=body.path, editor_path=where)


@router.get("/stop/files/versions", response_model=FileVersionsOut)
async def file_versions(path: str = Query(min_length=1)) -> FileVersionsOut:
    found = await get_sync_service().file_versions(path)
    if found is None:
        raise SyncNothingStopped(f"{path} is not one of the stopped round's files")
    return FileVersionsOut(
        path=found.path,
        ours=found.ours,
        theirs=found.theirs,
        base=found.base,
        take_theirs=found.take_theirs,
        binary=found.binary,
    )


@router.post("/continue", response_model=RoundOut)
async def continue_round() -> RoundOut:
    """Continue the stopped round once every file is answered: the resolved
    tree is validated, guarded, snapshotted, checked out and pushed."""
    return round_out(await get_sync_service().continue_round())


@router.post("/hold/confirm", response_model=RoundOut)
async def confirm_hold() -> RoundOut:
    """Apply the held deletions, and continue the round."""
    svc = get_sync_service()
    await svc.confirm_hold()
    return round_out(await svc.continue_round())


@router.post("/hold/restore", response_model=RoundOut)
async def restore_hold() -> RoundOut:
    """Keep the held files, and continue the round (it pushes them back)."""
    svc = get_sync_service()
    await svc.restore_hold(actor=_ACTOR)
    return round_out(await svc.continue_round())


# --- rolling a round back ------------------------------------------------------------------


@router.get("/runs/{run_id}/rollback-plan", response_model=RollbackPlanOut)
async def rollback_plan(run_id: int) -> RollbackPlanOut:
    shown = await get_sync_service().rollback_plan(run_id)
    return RollbackPlanOut(
        snapshot=shown.snapshot,
        snapshot_commit=shown.snapshot_commit,
        snapshot_time=shown.snapshot_time,
        reverses=[change_out(c) for c in shown.reverses],
        kept=list(shown.kept),
    )


@router.post("/runs/{run_id}/rollback", response_model=RoundOut)
async def rollback(run_id: int) -> RoundOut:
    """Put back what the round changed, as a new commit here; edits made
    since are kept."""
    return round_out(await get_sync_service().rollback(run_id, actor=_ACTOR))
