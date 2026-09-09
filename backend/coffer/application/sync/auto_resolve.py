"""Deterministic conflict auto-resolution (spec 010 amendment 2026-07-10).

Per conflicted path, the side whose last VAULT-REPO commit touching it is
newer wins. Commit time is when a change was captured by a sync run (a run
commits its export just before pulling), not when the user edited — so the
policy is precisely "the most recently synced edit wins"; with near-real-time
auto-sync on every machine the two coincide. Machine-independent, so every
machine picks the same winner; a timestamp tie keeps the merging machine's
side. ``manifest.json`` always resolves ours (byte-identical across
same-version machines; the schema gate runs before export). Anything the
policy cannot settle is left for the user's own git tooling (the UI points at
the remote repo) or ``coffer sync resolve``.

``credentials/*.enc`` blobs are the exception: commit time says who SYNCED
last, not whose ciphertext is newer — a machine re-exporting a months-old
orphaned blob commits "newest" and would win (the 2026-07-10 incident). Their
Fernet encryption timestamps order the actual content, so the fresher
encryption wins regardless of which side merged last.
"""

from __future__ import annotations

import asyncio

from coffer.application.audit_service import AuditService
from coffer.application.sync.ports import GitPort
from coffer.domain.audit import AuditEventType
from coffer.domain.sync.fernet_time import fernet_created_at

_MANIFEST = "manifest.json"


async def _credential_side(git: GitPort, path: str) -> str | None:
    """'ours'/'theirs' by embedded encryption time; None when either side is
    missing or unparseable (caller falls back to commit-time policy)."""
    ours_blob = await asyncio.to_thread(git.read_blob, "HEAD", path)
    theirs_blob = await asyncio.to_thread(git.read_blob, "MERGE_HEAD", path)
    ours_ts = fernet_created_at(ours_blob) if ours_blob is not None else None
    theirs_ts = fernet_created_at(theirs_blob) if theirs_blob is not None else None
    if ours_ts is None or theirs_ts is None:
        return None
    return "theirs" if theirs_ts > ours_ts else "ours"


async def auto_resolve(git: GitPort, audit: AuditService, paths: list[str]) -> list[str]:
    """Resolve ``paths`` newest-wins; return the paths still conflicted
    afterwards (empty = resolved and the merge commit finalized)."""
    ours: list[str] = []
    theirs: list[str] = []
    for path in paths:
        if path == _MANIFEST:
            ours.append(path)
            continue
        if path.startswith("credentials/") and path.endswith(".enc"):
            side = await _credential_side(git, path)
            if side is not None:
                (theirs if side == "theirs" else ours).append(path)
                continue
        ours_ts = await asyncio.to_thread(git.last_commit_ts, "HEAD", path)
        theirs_ts = await asyncio.to_thread(git.last_commit_ts, "MERGE_HEAD", path)
        if theirs_ts is not None and (ours_ts is None or theirs_ts > ours_ts):
            theirs.append(path)
        else:
            ours.append(path)
    if ours:
        await asyncio.to_thread(git.resolve, "ours", ours)
    if theirs:
        await asyncio.to_thread(git.resolve, "theirs", theirs)
    remaining = await asyncio.to_thread(git.conflicted_paths)
    if not remaining:
        await audit.record(
            AuditEventType.SYNC_AUTO_RESOLVED.value,
            actor="sync",
            details={"ours": len(ours), "theirs": len(theirs)},
        )
    return remaining
