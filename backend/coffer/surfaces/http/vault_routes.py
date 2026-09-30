"""``/api/v1/vault`` — the history of any vault file or folder, a version's
diff and content, restoring a version, recent changes, and the hand edits
validation refused (spec vault-storage "Show, compare and restore any version
of a vault file", "Keep the last valid version when a hand edit is invalid").

The use cases are ``coffer.application.vault.history_service``; this module
only shapes them for the wire. A restore is an ordinary vault write: the
caller states the fingerprint of what it last read (``GET /content`` without a
version reads the file as it is on disk now), and the result is audited as
``vault_file_restored`` after its commit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from coffer.application.audit_service import AuditService
from coffer.application.vault.history_service import (
    Restored,
    VaultHistoryService,
    VaultVersionNotFound,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.vault.writers import OP_RESTORE
from coffer.infrastructure.vault.actor_meta import commit_meta
from coffer.infrastructure.vault.instance import vault_repository, vault_writer
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.vault_schemas import (
    VaultChangesOut,
    VaultContentOut,
    VaultDiffOut,
    VaultHistoryOut,
    VaultProblemsOut,
    VaultRestoreIn,
    VaultRestoreOut,
    content_out,
    diff_out,
    problem_out,
    version_out,
)

router = APIRouter(prefix="/api/v1/vault", tags=["vault"], dependencies=[Depends(require_token)])


def get_vault_history(
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> VaultHistoryService:
    """The history service over this HOME's vault, auditing every restore."""

    async def record(result: Restored, actor: str) -> None:
        await audit.record(
            AuditEventType.VAULT_FILE_RESTORED.value,
            actor=actor,
            details={
                "path": result.path,
                "version": result.version,
                "restored_from": result.restored_from,
                "paths": list(result.paths),
            },
        )

    return VaultHistoryService(vault_repository(), vault_writer(), on_restored=record)


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
    path: str = Query(min_length=1),
    version: str = Query(min_length=4),
    history: VaultHistoryService = Depends(get_vault_history),  # noqa: B008
) -> VaultDiffOut:
    """What one version did to one file, as a unified diff."""
    return diff_out(await history.diff(path, version), version)


@router.get("/content", response_model=VaultContentOut)
async def vault_content(
    path: str = Query(min_length=1),
    version: str | None = Query(None, description="Omit for the file as it is on disk now"),
    history: VaultHistoryService = Depends(get_vault_history),  # noqa: B008
) -> VaultContentOut:
    """A file's content as a version left it, or as it is now, with its fingerprint."""
    if version is None:
        data = await history.current(path)
        if data is None:
            raise VaultVersionNotFound(f"no file at {path}")
        return content_out(path, None, data)
    return content_out(path, version, await history.content(path, version))


@router.post("/restore", response_model=VaultRestoreOut)
async def vault_restore(
    body: VaultRestoreIn,
    history: VaultHistoryService = Depends(get_vault_history),  # noqa: B008
    actor: str = Depends(get_actor),
) -> VaultRestoreOut:
    """Write a version back as a new commit naming the writer and the version
    it restored; a stale ``expected_fingerprint`` is 409 and changes nothing."""
    meta = commit_meta(OP_RESTORE, "", actor)
    result = await history.restore(
        body.path,
        body.version,
        expected_fingerprint=body.expected_fingerprint,
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


@router.get("/changes", response_model=VaultChangesOut)
async def vault_changes(
    prefix: str = Query("", description="Only commits under this path (default: the whole vault)"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    history: VaultHistoryService = Depends(get_vault_history),  # noqa: B008
) -> VaultChangesOut:
    """Recent commits across the vault, or under one prefix, newest first."""
    commits, next_cursor = await history.changes(prefix, limit=limit, cursor=cursor)
    within = prefix.rstrip("/") + "/" if prefix else ""
    return VaultChangesOut(
        changes=[version_out(c, within=within) for c in commits], next_cursor=next_cursor
    )


@router.get("/problems", response_model=VaultProblemsOut)
async def vault_problems(
    history: VaultHistoryService = Depends(get_vault_history),  # noqa: B008
) -> VaultProblemsOut:
    """Hand edits validation refused: still on disk, uncommitted, with ``HEAD``
    in effect until each is fixed."""
    return VaultProblemsOut(problems=[problem_out(f) for f in history.problems()])


__all__ = ["get_vault_history", "router"]
