"""What about vault convergence needs a person (the Overview list).

Read off the last recorded round, and only while a remote is configured:

- ``sync_conflict`` — git could not merge and nothing resolved it. The action
  is another round, once the person has resolved it in their own git;
- ``sync_deletions_held`` — the deletion guard held a round. The action opens
  the sync status, not the confirm: confirming deletions is an answer about a
  specific diff, and the Overview does not show it.

Every other status either succeeded, will be retried by the next round on its
own, or is the person's own choice (a disabled remote, a join not yet made).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.domain.sync.backup import BackupRemote
from coffer.domain.sync.convergence import ConvergeRun, ConvergeStatus

KIND = "sync"
_TITLE = "Sync"


class SyncRunsPort(Protocol):
    async def get_remote(self) -> BackupRemote | None: ...

    async def last_run(self) -> ConvergeRun | None: ...


class SyncAttentionSource:
    name = "sync"
    feature: str | None = "vault_sync"

    def __init__(self, *, sync: SyncRunsPort) -> None:
        self._sync = sync

    async def items(self) -> Sequence[AttentionItem]:
        if await self._sync.get_remote() is None:
            return []
        run = await self._sync.last_run()
        if run is None:
            return []
        if run.status is ConvergeStatus.CONFLICT:
            count = len(run.conflicts)
            files = "a file" if count == 1 else f"{count} files" if count else "files"
            return [
                AttentionItem(
                    kind=KIND,
                    uid=None,
                    title=_TITLE,
                    reason_code="sync_conflict",
                    reason=f"The last round could not merge {files}; resolve it in git.",
                    severity=Severity.ERROR,
                    action=AttentionAction(verb="run", method="POST", path="/api/v1/sync/run"),
                    since=run.started_at,
                )
            ]
        if run.status is ConvergeStatus.AWAITING_CONFIRMATION:
            pending = run.pending
            return [
                AttentionItem(
                    kind=KIND,
                    uid=None,
                    title=_TITLE,
                    reason_code="sync_deletions_held",
                    reason="A round is held because it would delete more than the guard allows.",
                    severity=Severity.WARNING,
                    action=AttentionAction(verb="review", method="GET", path="/api/v1/sync/status"),
                    since=pending.raised_at if pending is not None else run.started_at,
                )
            ]
        return []


__all__ = ["SyncAttentionSource", "SyncRunsPort"]
