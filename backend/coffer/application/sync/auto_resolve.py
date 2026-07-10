"""Deterministic conflict auto-resolution (spec 010 amendment 2026-07-10).

Newest-wins per conflicted path: the side whose last commit touching the path
is newer wins — machine-independent, so every machine picks the same winner; a
timestamp tie keeps the merging machine's side. ``manifest.json`` always
resolves ours (the schema gate has already run, so ours is the highest schema
this vault may carry). Anything the policy cannot settle is left for the
user's own git tooling (the UI points at the remote repo) or
``coffer sync resolve``.
"""

from __future__ import annotations

import asyncio

from coffer.application.audit_service import AuditService
from coffer.application.sync.ports import GitPort
from coffer.domain.audit import AuditEventType

_MANIFEST = "manifest.json"


async def auto_resolve(git: GitPort, audit: AuditService, paths: list[str]) -> list[str]:
    """Resolve ``paths`` newest-wins; return the paths still conflicted
    afterwards (empty = resolved and the merge commit finalized)."""
    ours: list[str] = []
    theirs: list[str] = []
    for path in paths:
        if path == _MANIFEST:
            ours.append(path)
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
