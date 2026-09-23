"""The remote-configuration half of ``ConvergeService`` (spec vault-sync).

Split out for the file-size tier, the same way ``service_machines.py`` and
``service_history.py`` were, and along a real seam: the rest of the service
runs rounds against a remote, while this decides which remote there is. Kept
as a mixin rather than a second service because configuring the remote takes
the round's lock, probes it through the same mirror factory and resolves the
same push credential — a second object holding all three would be the service
under another name.

Two refusals live here besides reachability. A working tree that would overlap
the vault's own directories is refused before any git runs (the round mirrors
the vault *into* the tree and ``reset --hard``s it), and the domain has already
refused a URL or branch that git would read as an option.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from coffer.domain.error_base import CofferError
from coffer.domain.sync.backup import DEFAULT_WORKTREE, BackupRemote, worktree_conflict
from coffer.domain.sync.errors import BackupRemoteInvalid

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.convergence import ConvergeRound
    from coffer.application.sync.ports import (
        ConvergenceStatePort,
        GitMirrorPort,
        SyncRemoteRepoPort,
    )
    from coffer.domain.sync.convergence import ConvergeRun


class RemoteMixin:
    """Declares what it borrows from the service it is mixed into.

    The annotations below are the contract, not state: ``ConvergeService``
    assigns every one of them in its constructor. Spelling them here is what
    lets this half be type-checked on its own instead of trusting that the
    other half happens to provide them.
    """

    _remotes: SyncRemoteRepoPort
    _state: ConvergenceStatePort
    _lock: asyncio.Lock
    _mirror_factory: Callable[[Path], GitMirrorPort]
    _protected_roots: list[Path]
    _coffer_dir: Path | None
    _round_factory: Callable[[GitMirrorPort, str], ConvergeRound]

    async def _token(self, remote: BackupRemote) -> str | None:
        raise NotImplementedError  # pragma: no cover - provided by ConvergeService

    async def get_remote(self) -> BackupRemote | None:
        return await self._remotes.get()

    async def set_remote(self, remote: BackupRemote) -> BackupRemote:
        """Store the remote, having first proved it is reachable.

        A remote that cannot be reached is rejected at the front door rather
        than discovered by a worker tick an hour later: the user is here now,
        with the URL and the credential in front of them, and that is the only
        moment the fix is cheap.

        Under the round's lock, because it prepares the working tree — an
        ``ensure_repo`` landing mid-round could repoint ``origin`` between a
        fetch and a push, and a stored remote that changed under a running
        round would have that round push to a repository it never merged.
        """
        worktree = Path(remote.worktree_path).expanduser()
        if not worktree.is_absolute():
            raise BackupRemoteInvalid(f"worktree_path must be absolute: {remote.worktree_path}")
        self._check_worktree(worktree)
        async with self._lock:
            mirror = self._mirror_factory(worktree)
            try:
                await mirror.ensure_repo(remote_url=remote.url, branch=remote.branch)
                await mirror.fetch(token=await self._token(remote))
            except CofferError as e:
                # The adapter has already redacted the push credential out of
                # the message, and this one is never audited.
                raise BackupRemoteInvalid(str(e)) from e
            await self._remotes.set(remote)
        return remote

    def _check_worktree(self, worktree: Path) -> None:
        """Refuse a working tree that would mirror the vault into itself or
        take Coffer's own directory with it on the next ``reset --hard``."""
        if self._coffer_dir is None and not self._protected_roots:
            return
        coffer_dir = self._coffer_dir or Path(DEFAULT_WORKTREE).expanduser().parent
        reason = worktree_conflict(
            worktree,
            mirrored_roots=self._protected_roots,
            coffer_dir=coffer_dir,
            default_worktree=coffer_dir / Path(DEFAULT_WORKTREE).name,
        )
        if reason is not None:
            raise BackupRemoteInvalid(reason)

    async def clear_remote(self) -> bool:
        """Forget the remote. Idempotent, and it leaves the vault alone.

        The pointer goes with it: a remote configured again later must run the
        join detection rather than assume the old base still means anything.

        Under the round's lock: a round in flight ends by writing the pointer,
        and a clear that slipped in before that write would be undone by it —
        the next ``adopt`` would then skip the join detection on the strength
        of a base the user had asked to forget.
        """
        async with self._lock:
            if await self._remotes.get() is None:
                return False
            await self._remotes.clear()
            await self._state.set_pending(None)
            # The pointer and the held paths go with it. Both describe a
            # position in one remote's history; kept across a clear, they
            # would let a later `adopt` skip the join detection entirely — the
            # route-around that detection exists to prevent.
            await self._state.clear_pointer()
            await self._state.clear_holds()
        return True

    async def last_run(self) -> ConvergeRun | None:
        return await self._remotes.last_run()

    async def joined(self) -> bool:
        """Whether this machine has joined the remote — by the round's own
        predicate (``ConvergeRound.is_joining``), so the status surface and
        the next round can never disagree."""
        remote = await self._remotes.get()
        if remote is None or await self._state.pointer() is None:
            return False
        mirror = self._mirror_factory(Path(remote.worktree_path).expanduser())
        return not await self._round_factory(mirror, remote.branch).is_joining()
