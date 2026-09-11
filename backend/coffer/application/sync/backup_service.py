"""Back the vault up to one user-owned git remote (spec vault-export-import ``## Backup``).

A backup run is an ordinary export into a directory that happens to be a git
working tree, followed by a commit when the export changed and a push. Nothing
converges, nothing merges, nothing arbitrates: the remote is a copy, never a
system of record (constitution 0.5.0 Principle I exception).

Two rules shape the whole module:

* **A commit is never rolled back because the push failed.** The local history
  is the first layer of recovery, so a failed push leaves its commit behind and
  the next run carries it out — which is why a run with nothing new to export
  still pushes when something is outstanding.
* **The push credential is resolved at push time and nowhere else.** It is
  handed to the mirror for the single invocation that needs it, never stored on
  this service, never audited, and any error text is re-redacted before it is
  recorded even though the adapter already redacted it.

``run_once`` therefore does not raise for a failure the user can be told about:
it returns a :class:`BackupRun` carrying the status, so the worker's loop never
has to decide what is survivable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.sync.ports import GitMirrorPort
from coffer.application.sync.service import SyncService
from coffer.domain.audit import AuditEventType
from coffer.domain.error_base import CofferError
from coffer.domain.sync.backup import (
    DEFAULT_BRANCH,
    DEFAULT_WORKTREE,
    BackupRemote,
    BackupRun,
    BackupRunStatus,
    redact,
)
from coffer.domain.sync.errors import BackupRemoteInvalid
from coffer.domain.sync.models import ExportSummary, ImportSummary

_logger = logging.getLogger(__name__)

#: Key the push credential is materialised under; it exists for the length of
#: one ``push`` call and is never written anywhere.
_TOKEN_KEY = "token"

#: A staged diff confined to these paths is not a change worth committing.
#: ``manifest.json`` carries the bundle's creation time, which every export
#: restamps — see ``BackupService._commit_if_changed``.
_MANIFEST_ONLY = frozenset({"manifest.json"})


class BackupRemoteRepoPort(Protocol):
    """Storage for the single backup remote and its last run.

    A port rather than the concrete repository so the application layer keeps
    no infrastructure import (CODE-005); the composition root injects
    ``SqlAlchemySyncRemoteRepo``.
    """

    async def get(self) -> BackupRemote | None: ...

    async def set(self, remote: BackupRemote) -> None: ...

    async def clear(self) -> None: ...

    async def record_run(self, run: BackupRun) -> None: ...

    async def last_run(self) -> BackupRun | None: ...


def _commit_message(summary: ExportSummary) -> str:
    """A commit message naming the counts per area (spec ``## Backup``).

    The history is meant to be read with the user's own git tools, so the
    message says what changed in vault terms rather than repeating a timestamp
    the commit already carries.
    """
    counts = " ".join(f"{area.area}={area.count}" for area in summary.areas)
    message = f"coffer backup: {counts}" if counts else "coffer backup"
    if summary.credentials_included:
        message += " (+credentials)"
    return message


class BackupService:
    """Configure the backup remote, run a backup, restore from one."""

    def __init__(
        self,
        *,
        remotes: BackupRemoteRepoPort,
        sync: SyncService,
        mirror_factory: Callable[[Path], GitMirrorPort],
        credentials: CredentialResolver,
        audit: AuditService,
    ) -> None:
        self._remotes = remotes
        # The real ``SyncService``, deliberately: exporting through it reuses
        # its own lock, so a manual export and a backup run cannot interleave
        # over the same vault.
        self._sync = sync
        # A factory, because the working tree is part of the remote's config
        # and can change under the user without a daemon restart.
        self._mirror_factory = mirror_factory
        self._credentials = credentials
        self._audit = audit

    async def configure(self, remote: BackupRemote) -> None:
        await self._remotes.set(remote)

    async def get(self) -> BackupRemote | None:
        return await self._remotes.get()

    async def clear(self) -> None:
        await self._remotes.clear()

    async def status(self) -> tuple[BackupRemote | None, BackupRun | None]:
        return await self._remotes.get(), await self._remotes.last_run()

    async def run_once(self) -> BackupRun:
        """Export, commit if that changed anything, push if anything is outstanding.

        Returns the run rather than raising for anything the user can act on —
        an unreachable remote, a rejected push, a credential that is not in the
        store. Genuinely unexpected exceptions still propagate; the worker logs
        and swallows those so one bug cannot silence the backup forever.
        """
        remote = await self._remotes.get()
        if remote is None or not remote.enabled:
            # Not a run: nothing was exported and no history moved, so there is
            # no outcome to record and nothing to audit.
            return BackupRun(status=BackupRunStatus.NO_CHANGE, ran_at=datetime.now(tz=UTC))
        return await self._run(remote)

    async def _run(self, remote: BackupRemote) -> BackupRun:
        ran_at = datetime.now(tz=UTC)
        worktree = Path(remote.worktree_path).expanduser()
        mirror = self._mirror_factory(worktree)
        try:
            await mirror.ensure_repo(remote_url=remote.url, branch=remote.branch)
            summary = await self._sync.export_bundle(
                str(worktree), with_credentials=remote.include_credentials
            )
            commit = await self._commit_if_changed(mirror, summary)
            outstanding = commit is not None or await mirror.has_unpushed(branch=remote.branch)
        except CofferError as exc:
            return await self._finish(
                BackupRun(status=BackupRunStatus.EXPORT_FAILED, error=str(exc), ran_at=ran_at)
            )
        if not outstanding:
            return await self._finish(BackupRun(status=BackupRunStatus.NO_CHANGE, ran_at=ran_at))
        return await self._push(mirror, remote, commit=commit, ran_at=ran_at)

    @staticmethod
    async def _commit_if_changed(mirror: GitMirrorPort, summary: ExportSummary) -> str | None:
        """Commit only when the export differs from what the tree already held.

        Determinism is what makes this reliable — but it stops one file short.
        ``manifest.json`` carries the bundle's creation time, so every export
        rewrites it even when the vault has not changed, and a diff that
        touches nothing else is a restamped manifest rather than a change to
        back up. Committing it anyway would put an entry in the history for
        every tick, which is exactly what ``restore --at <date>`` has to see
        through.
        """
        if not await mirror.stage_all():
            return None
        staged = set(await mirror.staged_paths())
        if staged <= _MANIFEST_ONLY:
            return None
        return await mirror.commit(_commit_message(summary))

    async def _push(
        self,
        mirror: GitMirrorPort,
        remote: BackupRemote,
        *,
        commit: str | None,
        ran_at: datetime,
    ) -> BackupRun:
        token: str | None = None
        try:
            token = self._token(remote)
            await mirror.push(branch=remote.branch, token=token)
        except CofferError as exc:
            # The commit stays. Rolling it back would throw away the only copy
            # of the change that exists anywhere while the remote is down.
            return await self._finish(
                BackupRun(
                    status=BackupRunStatus.PUSH_FAILED,
                    commit=commit,
                    error=redact(str(exc), token),
                    ran_at=ran_at,
                )
            )
        pushed = commit if commit is not None else await mirror.head()
        return await self._finish(
            BackupRun(status=BackupRunStatus.OK, commit=pushed, ran_at=ran_at)
        )

    def _token(self, remote: BackupRemote) -> str | None:
        """Materialise the push credential, or None when the remote needs none."""
        if not remote.credential_ref:
            return None
        return self._credentials.materialize({_TOKEN_KEY: remote.credential_ref})[_TOKEN_KEY]

    async def _finish(self, run: BackupRun) -> BackupRun:
        """Record the run and audit it — exactly once per run.

        The audit payload carries the status and the commit only: never the
        token, and never git's raw stderr, which echoes back the URL it tried.
        """
        await self._remotes.record_run(run)
        await self._audit.record(
            AuditEventType.VAULT_BACKED_UP.value,
            actor="sync",
            details={"status": str(run.status), "commit": run.commit},
        )
        _logger.info("backup run finished: %s", run.status)
        return run

    async def restore(self, *, at: str | None = None, from_url: str | None = None) -> ImportSummary:
        """Fetch the backup, optionally move to an earlier revision, then import.

        Always explicit — nothing here ever runs on a timer. ``at`` accepts a
        sha, a ref or a ``YYYY-MM-DD`` date, because the failure this exists
        for (something deleted and noticed a week later) cannot be served by
        the tip: a backup mirrors deletions as faithfully as additions.
        """
        remote = await self._remotes.get()
        if remote is None and from_url is None:
            raise BackupRemoteInvalid("no backup remote is configured; name a url to restore from")
        url = from_url or (remote.url if remote else "")
        branch = remote.branch if remote else DEFAULT_BRANCH
        worktree = Path(remote.worktree_path if remote else DEFAULT_WORKTREE).expanduser()
        mirror = self._mirror_factory(worktree)
        token = self._token(remote) if remote else None
        await self._open_worktree(mirror, url=url, branch=branch, token=token, cloning=from_url)
        await mirror.fetch(token=token)
        try:
            if at is not None:
                await mirror.checkout(await mirror.resolve_revision(at))
            return await self._sync.import_bundle(str(worktree))
        finally:
            # Even a failed import leaves the tree on its branch: a detached
            # HEAD left behind would make the next backup run commit nowhere.
            await mirror.checkout_branch(branch)

    @staticmethod
    async def _open_worktree(
        mirror: GitMirrorPort,
        *,
        url: str,
        branch: str,
        token: str | None,
        cloning: str | None,
    ) -> None:
        """Clone when restoring onto a machine with no working tree yet."""
        if cloning is not None and await mirror.head() is None:
            await mirror.clone(remote_url=url, branch=branch, token=token)
            return
        await mirror.ensure_repo(remote_url=url, branch=branch)
