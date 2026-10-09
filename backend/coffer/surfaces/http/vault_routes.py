"""``/api/v1/vault`` — the history of a vault file or folder, a version's
diff, restoring a version, and the hand edits validation refused (spec
vault-storage "Show and restore any version of a vault file or folder", "List
the hand edits the vault kept out").

The use cases are ``coffer.application.vault.history_service``; this module
only shapes them for the wire. The web UI reads a knowledge document's history
at ``knowledge/<collection>/…`` and a skill's at ``skills/<name>/``. A restore
is an ordinary vault write — a new commit naming the writer and the version it
put back — audited as ``vault_file_restored`` after its commit.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from coffer.application.audit_service import AuditService
from coffer.application.vault.history_service import Restored, VaultHistoryService
from coffer.domain.audit import AuditEventType
from coffer.domain.audit_diff import commit_change
from coffer.domain.vault.writers import OP_RESTORE
from coffer.infrastructure.vault.actor_meta import commit_meta
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.vault_schemas import (
    VaultDiffOut,
    VaultHistoryOut,
    VaultProblemsOut,
    VaultRestoreIn,
    VaultRestoreOut,
    file_diff_out,
    problem_out,
    version_out,
)

router = APIRouter(prefix="/api/v1/vault", tags=["vault"], dependencies=[Depends(require_token)])


def get_vault_history(
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> VaultHistoryService:
    """The history service over this HOME's vault, auditing every restore."""

    repo = vault_repository()

    async def record(result: Restored, actor: str) -> None:
        details: dict[str, Any] = {
            "path": result.path,
            "version": result.version,
            "restored_from": result.restored_from,
            "paths": list(result.paths),
        }
        if result.version is not None:
            # What the restore changed, with the diff of knowledge and skill
            # text (never of config; ``secret/`` is not restored at all).
            details.update(
                await asyncio.to_thread(commit_change, repo.read, result.version, result.paths)
            )
        await audit.record(AuditEventType.VAULT_FILE_RESTORED.value, actor=actor, details=details)

    return VaultHistoryService(repo, vault_writer(), on_restored=record)


@router.get("/history", response_model=VaultHistoryOut)
async def vault_history(
    path: str = Query(min_length=1, description="A file, or a folder ending in /"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    history: VaultHistoryService = Depends(get_vault_history),  # noqa: B008
) -> VaultHistoryOut:
    """The versions of a file or folder, newest first, each naming its writer."""
    page = await history.versions(path, limit=limit, cursor=cursor)
    return VaultHistoryOut(
        path=page.path,
        versions=[
            version_out(v.commit, within=page.path, removed=v.removed) for v in page.versions
        ],
        next_cursor=page.next_cursor,
    )


@router.get("/diff", response_model=VaultDiffOut)
async def vault_diff(
    path: str = Query(min_length=1, description="A file, or a folder ending in /"),
    version: str = Query(min_length=4),
    against: Literal["previous", "current"] = Query("previous"),
    history: VaultHistoryService = Depends(get_vault_history),  # noqa: B008
) -> VaultDiffOut:
    """What one version changed (``previous``), or how the path differs now
    from how that version left it (``current``), as one unified diff per file."""
    found = await history.diff(path, version, against)
    return VaultDiffOut(
        path=found.path,
        version=found.version,
        against=found.against,
        files=[file_diff_out(f) for f in found.files],
    )


@router.post("/restore", response_model=VaultRestoreOut)
async def vault_restore(
    body: VaultRestoreIn,
    history: VaultHistoryService = Depends(get_vault_history),  # noqa: B008
    actor: str = Depends(get_actor),
) -> VaultRestoreOut:
    """Write a version back as a new commit naming the writer and the version
    it restored; a path changed since ``expected_current`` is 409 and changes
    nothing."""
    meta = commit_meta(OP_RESTORE, "", actor)
    result = await history.restore(
        body.path,
        body.version,
        expected_current=body.expected_current,
        actor=actor,
        writer=meta.writer,
        agent=meta.agent,
    )
    return VaultRestoreOut(
        path=result.path,
        version=result.version,
        restored_from=result.restored_from,
        paths=list(result.paths),
    )


@router.get("/problems", response_model=VaultProblemsOut)
async def vault_problems() -> VaultProblemsOut:
    """Hand edits validation refused: still on disk, uncommitted, with ``HEAD``
    in effect until each is fixed."""
    found = vault_writer().problems()
    return VaultProblemsOut(
        problems=[problem_out(f) for _path, items in sorted(found.items()) for f in items]
    )


__all__ = ["get_vault_history", "router"]
