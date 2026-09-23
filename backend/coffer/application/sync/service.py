"""Vault sync service (spec vault-sync; ADR vault-sync).

Owns the remote's configuration, the lock, the audit trail and the master-key
bootstrap, and delegates the algorithm to :class:`ConvergeRound`. The split is
deliberate: the round can then be tested against a fake mirror with no database
anywhere near it, and this file stays about *policy* — when a round may run,
what a held round means, what gets recorded.

One lock guards everything that writes the vault or the working tree. The
knowledge tidy pass takes the same one (spec vault-sync ``## Unattended
rewriters``): both rewrite vault content, and an export taken half-way through
a rewrite is a torn snapshot that git would read as a deliberate change.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.sync.convergence import ConvergeRound
from coffer.application.sync.convergence_ops import refuse_newer_layout
from coffer.application.sync.joining import JoinPreview
from coffer.application.sync.ports import (
    BundlePort,
    ConvergenceStatePort,
    CredentialSyncPort,
    GitMirrorPort,
    MasterKeyPort,
    SyncRemoteRepoPort,
)
from coffer.application.sync.service_history import HistoryMixin
from coffer.application.sync.service_machines import MachinesMixin
from coffer.application.sync.service_remote import RemoteMixin
from coffer.domain.audit import AuditEventType
from coffer.domain.error_base import CofferError
from coffer.domain.sync.backup import BackupRemote
from coffer.domain.sync.convergence import ConvergeRun, ConvergeStatus, PendingConfirmation
from coffer.domain.sync.errors import MasterKeyFileInvalid

#: Materialised for the length of one push and never written anywhere.
_TOKEN_KEY = "token"


class ConvergeService(RemoteMixin, MachinesMixin, HistoryMixin):
    """Configure the remote, run a round, resolve a held one."""

    def __init__(
        self,
        *,
        remotes: SyncRemoteRepoPort,
        state: ConvergenceStatePort,
        round_factory: Callable[[GitMirrorPort, str], ConvergeRound],
        mirror_factory: Callable[[Path], GitMirrorPort],
        bundle_factory: Callable[[Path], BundlePort],
        set_machine_name: Callable[[str], None],
        credentials: CredentialResolver,
        credential_store: CredentialSyncPort,
        master_key: MasterKeyPort,
        audit: AuditService,
        lock: asyncio.Lock | None = None,
        protected_roots: Sequence[Path] = (),
        coffer_dir: Path | None = None,
    ) -> None:
        self._remotes = remotes
        self._state = state
        self._round_factory = round_factory
        # A factory because the working tree is part of the remote's config and
        # can change under the user without a daemon restart.
        self._mirror_factory = mirror_factory
        self._bundle_factory = bundle_factory
        self._set_machine_name = set_machine_name
        self._credentials = credentials
        self._credential_store = credential_store
        self._master_key = master_key
        self._audit = audit
        # Shared with the tidy worker, which is why it is injectable.
        self._lock = lock or asyncio.Lock()
        # The live directories a working tree may not overlap: the mirrored
        # roots and Coffer's own directory. Empty means "no check", which is
        # only right for a test that pins every root under ``tmp_path``.
        self._protected_roots = [Path(r).expanduser() for r in protected_roots]
        self._coffer_dir = Path(coffer_dir).expanduser() if coffer_dir is not None else None

    @property
    def lock(self) -> asyncio.Lock:
        """The vault-write lock, for anything else that rewrites vault content."""
        return self._lock

    # --- rounds -------------------------------------------------------------

    async def run_once(
        self,
        *,
        join_choice: str | None = None,
        confirmed: PendingConfirmation | None = None,
        adopt: bool = False,
    ) -> ConvergeRun:
        """One converge round. Never raises for something the user can be told.

        The worker calls this on a timer and a surface calls it on demand; both
        get a ``ConvergeRun`` back, so neither has to decide what is survivable.
        Only ``adopt`` may join: on a machine with no pointer any other round
        reports ``awaiting_join`` and does nothing else.
        """
        started = datetime.now(tz=UTC)
        remote = await self._remotes.get()
        if remote is None or not remote.enabled:
            return ConvergeRun(
                status=ConvergeStatus.DISABLED, started_at=started, finished_at=started
            )
        async with self._lock:
            try:
                run = await self._run(
                    remote, join_choice=join_choice, confirmed=confirmed, adopt=adopt
                )
            except CofferError as e:
                run = ConvergeRun(
                    status=ConvergeStatus.FAILED,
                    started_at=started,
                    finished_at=datetime.now(tz=UTC),
                    error=_redact(str(e), await self._token(remote)),
                )
        await self._record(run)
        return run

    async def preview_join(self, *, choice: str | None = None) -> JoinPreview:
        """State the join a round would make, applying nothing (spec vault-sync
        "Report a join before applying it"). Under the lock: it fetches and
        serializes into the working tree, as a round does."""
        remote = await self._remotes.get()
        if remote is None or not remote.enabled:
            return JoinPreview(joining=False)
        async with self._lock:
            mirror = self._mirror_factory(Path(remote.worktree_path).expanduser())
            await mirror.ensure_repo(remote_url=remote.url, branch=remote.branch)
            round_ = self._round_factory(mirror, remote.branch)
            return await round_.preview_join(token=await self._token(remote), choice=choice)

    async def _run(
        self,
        remote: BackupRemote,
        *,
        join_choice: str | None,
        confirmed: PendingConfirmation | None,
        adopt: bool,
    ) -> ConvergeRun:
        mirror = self._mirror_factory(Path(remote.worktree_path).expanduser())
        await mirror.ensure_repo(remote_url=remote.url, branch=remote.branch)
        round_ = self._round_factory(mirror, remote.branch)
        return await round_.run(
            token=await self._token(remote),
            join_choice=join_choice,
            confirmed=confirmed,
            adopt=adopt,
        )

    async def confirm(self) -> ConvergeRun:
        """Accept a round the deletion guard held, and let it finish.

        The round is re-derived rather than resumed. Serialization is
        deterministic, so an unchanged vault against an unchanged remote yields
        exactly the diff the user was shown — and the guard is waived only for
        the remote tip the hold was raised against. If the remote moved in the
        meantime the guard runs again and the round is held afresh, because a
        confirmation is an answer about a specific set of documents, not a
        standing permission to delete.
        """
        pending = await self._state.pending()
        if pending is None:
            raise SyncNothingPendingError()
        await self._state.set_pending(None)
        await self._audit.record(
            AuditEventType.SYNC_CONFIRMED.value,
            actor="user",
            details={"direction": pending.direction.value, "paths": len(pending.paths)},
        )
        return await self.run_once(confirmed=pending)

    async def reject(self) -> None:
        """Discard a held round, returning the working tree to the pointer.

        The vault was never touched — the guard runs before the apply — so
        rejecting only has to undo the tree.
        """
        pending = await self._state.pending()
        if pending is None:
            raise SyncNothingPendingError()
        remote = await self._remotes.get()
        pointer = await self._state.pointer()
        # Under the lock: this moves the working tree, and the appliers read
        # every document out of that tree. Landing mid-apply would hand them
        # pre-merge content for paths the round is about to mark absorbed.
        async with self._lock:
            if remote is not None and pointer is not None:
                mirror = self._mirror_factory(Path(remote.worktree_path).expanduser())
                await mirror.reset_hard(pointer)
            await self._state.set_pending(None)
        await self._audit.record(
            AuditEventType.SYNC_REJECTED.value,
            actor="user",
            details={"direction": pending.direction.value},
        )

    async def rollback(self) -> ConvergeRun:
        """Undo the last applied round from its pre-apply snapshot.

        The snapshot's tree is by construction the vault's state immediately
        before the apply, so this is the same machinery run backwards: diff
        from where the vault is now to where it was, and apply that.
        """
        remote = await self._remotes.get()
        pointer = await self._state.pointer()
        if remote is None or pointer is None:
            raise SyncNothingToRollBackError()
        async with self._lock:
            mirror = self._mirror_factory(Path(remote.worktree_path).expanduser())
            snapshots = await mirror.tags("coffer/pre-apply/")
            if not snapshots:
                raise SyncNothingToRollBackError()
            target = await mirror.resolve_revision(snapshots[0])
            round_ = self._round_factory(mirror, remote.branch)
            # The pointer does not move. ``reverse_to`` leaves the working
            # tree where it was, so the reverted vault is now an ordinary local
            # change: the next round publishes the undo instead of re-deriving
            # the diff that caused it.
            run = await round_.reverse_to(pointer, target)
        await self._audit.record(
            AuditEventType.SYNC_ROLLED_BACK.value, actor="user", details={"to": target[:12]}
        )
        return run

    async def restore(self, *, at: str | None = None) -> ConvergeRun:
        """Bring the vault to an earlier point in the remote's history.

        The history is the backup: a document deleted last week returns by
        naming a revision or a date, and everything the vault gained since is
        untouched — which is why the deletions in that diff are dropped rather
        than applied. "Bring back last week's note" is not also "throw away this
        week's".

        The pointer does **not** move. It names the commit this vault has
        provably absorbed, and a restore does not un-absorb anything: the vault
        now holds everything it held a moment ago *plus* what came back. Moving
        it to the older commit would make the next round read the re-added
        documents as unchanged since the base and let the remote's deletion of
        them win all over again, quietly undoing the restore. Left where it is,
        the next round publishes the recovered documents as the ordinary
        additions they are.
        """
        remote = await self._remotes.get()
        pointer = await self._state.pointer()
        if remote is None or pointer is None:
            raise SyncNothingToRollBackError()
        async with self._lock:
            mirror = self._mirror_factory(Path(remote.worktree_path).expanduser())
            await mirror.ensure_repo(remote_url=remote.url, branch=remote.branch)
            await mirror.fetch(token=await self._token(remote))
            target = await mirror.resolve_revision(at or f"origin/{remote.branch}")
            # A restore reads its documents out of ``target``, so ``target`` is
            # the tree whose layout must be legible here.
            await refuse_newer_layout(mirror, target)
            round_ = self._round_factory(mirror, remote.branch)
            run = await round_.reverse_to(pointer, target, delete=False)
        return run

    async def rebuild(self) -> ConvergeRun:
        """Rebuild this machine from the remote, discarding local-only documents.

        Offered where the publish-side guard holds a round (spec vault-sync
        ``### Joining a remote``): a vault that lost its files has no other
        honest answer, since confirming would publish the loss and rejecting
        would refuse the same round forever. Destructive on purpose, and never
        reached without the user asking for it by name.
        """
        remote = await self._remotes.get()
        if remote is None:
            raise SyncNothingToRollBackError()
        async with self._lock:
            mirror = self._mirror_factory(Path(remote.worktree_path).expanduser())
            await mirror.ensure_repo(remote_url=remote.url, branch=remote.branch)
            await mirror.fetch(token=await self._token(remote))
            tip = await mirror.resolve_revision(f"origin/{remote.branch}")
            # The most destructive read of the remote there is — this vault
            # becomes that tree — so it is the last place to skip the layout
            # check. Unlike a round, this raises out to the surface: a rebuild
            # is a user asking for something now, and the answer is 409 and
            # "upgrade this machine first", not a silent partial vault.
            await refuse_newer_layout(mirror, tip)
            run = await self._round_factory(mirror, remote.branch).rebuild_to(tip)
            await self._state.set_pointer(tip)
            await self._state.set_pending(None)
        await self._audit.record(
            AuditEventType.SYNC_ROLLED_BACK.value,
            actor="user",
            details={"rebuild": True, "to": tip[:12]},
        )
        return run

    # --- credentials --------------------------------------------------------

    async def _token(self, remote: BackupRemote) -> str | None:
        """Resolve the push credential, for the one call that needs it.

        Never stored on this service, never audited, and the caller re-redacts
        any error text even though the adapter already did.
        """
        if not remote.credential_ref:
            return None
        resolved = await asyncio.to_thread(
            self._credentials.materialize, {_TOKEN_KEY: remote.credential_ref}
        )
        token = resolved.get(_TOKEN_KEY)
        return str(token) if token is not None else None

    def key_fingerprint(self) -> str | None:
        """A short SHA-256 fingerprint of the master key, never the key.

        Two machines showing the same fingerprint hold the same key. It rides
        in each machine's descriptor, so the machines table can say outright
        that another machine's credentials will not decrypt here.
        """
        key = self._master_key.export_key()
        return hashlib.sha256(key).hexdigest()[:12] if key else None

    async def export_key(self) -> str:
        key = self._master_key.export_key()
        if key is None:
            raise MasterKeyFileInvalid("<export>", "no master key on this machine to export")
        await self._audit.record(AuditEventType.MASTER_KEY_EXPORTED.value, actor="sync")
        return key.decode("utf-8")

    async def import_key(self, material: str) -> list[str]:
        raw = material.strip().encode("utf-8")
        if not raw:
            raise MasterKeyFileInvalid("<import>", "no key material supplied")
        try:
            await asyncio.to_thread(self._master_key.install_key, raw)
        except ValueError as e:
            raise MasterKeyFileInvalid("<import>", "not a valid Fernet key") from e
        await self._audit.record(AuditEventType.MASTER_KEY_IMPORTED.value, actor="sync")
        return await asyncio.to_thread(self._credential_store.locked_refs)

    # --- recording ----------------------------------------------------------

    async def _record(self, run: ConvergeRun) -> None:
        waiting = run.hold_already_reported or run.status is ConvergeStatus.AWAITING_JOIN
        if waiting and await self._remotes.refresh_run(run):
            # The same confirmation the user has not answered yet. It is one
            # situation, and the timer re-deriving it every interval is not a
            # new one: the row that first reported it is re-stamped, and no
            # audit event is written either, so a vault waiting a week is a
            # single entry everywhere a person might read it (FR-092).
            return
        await self._remotes.record_run(run)
        if run.status is ConvergeStatus.DISABLED:
            return
        await self._audit.record(
            AuditEventType.SYNC_RUN.value,
            actor="sync",
            details={
                "status": run.status.value,
                "join": run.join.value if run.join else None,
                "applied": run.applied.counts(),
                "published": run.published.counts(),
                "conflicts": len(run.conflicts),
                "agent_resolved": len(run.agent_resolved),
                "failures": len(run.failures),
                "guard": run.pending.direction.value if run.pending else None,
            },
        )


def _redact(text: str, token: str | None) -> str:
    return text.replace(token, "***") if token else text


class SyncNothingPendingError(CofferError):
    """Nothing is held at the deletion guard. Maps to 409."""

    code = "SYNC_NOTHING_PENDING"

    def __init__(self) -> None:
        super().__init__("no converge round is waiting for confirmation")


class SyncNothingToRollBackError(CofferError):
    """No pre-apply snapshot to return to. Maps to 409."""

    code = "SYNC_NOTHING_TO_ROLL_BACK"

    def __init__(self) -> None:
        super().__init__("no pre-apply snapshot to roll back to")
