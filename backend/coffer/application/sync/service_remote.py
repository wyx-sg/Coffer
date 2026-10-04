"""The remote half of ``SyncService`` (spec vault-sync "Allow at most one
user-owned sync remote").

The remote is machine-local configuration (``local/sync/remote.json``): which
repository this machine converges with, on which branch, how often, and
whether ``secret/`` travels. Setting it adds ``origin`` to the vault
repository and sets whether ciphertext is committed; clearing it removes both
and forgets the round waiting for a person, which was a question about that
remote's history. Checking a remote looks at it without keeping anything, so
the setup form can say what it holds before it is saved.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from coffer.domain.secret_errors import SecretMissing
from coffer.domain.sync.errors import SyncNothingToRestore, SyncRemoteExists
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.stops import conflict_from_json, stop_from_json, to_json
from coffer.domain.vault.remote_errors import RemoteFailed, RemoteProblem

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.round_engine import RoundEngine
    from coffer.application.sync.round_ports import RemoteStorePort, TokenPort
    from coffer.application.sync.service_ports import RemoteProbePort
    from coffer.application.sync.views import RemoteCheck


class RemoteMixin:
    """Declares what it borrows from ``SyncService``, which assigns each."""

    _engine: RoundEngine
    _remotes: RemoteStorePort
    _token: TokenPort
    _probe: RemoteProbePort
    _lock: asyncio.Lock

    async def _locked(self, fn: Callable[[], Any]) -> Any:
        raise NotImplementedError  # pragma: no cover - provided by SyncService

    async def get_remote(self) -> SyncRemote | None:
        return await asyncio.to_thread(self._remotes.get)

    async def set_remote(self, remote: SyncRemote) -> SyncRemote:
        """Keep ``remote`` and point the vault's ``origin`` at it.

        The push token is resolved here once, so a token pointed at a URL it
        was never approved for is held for the person now rather than at the
        next round (spec vault-sync "Hold a push token pointed at a new URL
        until approved"): the remote is kept, the approval names it, and the
        error says so.
        """

        def apply() -> None:
            d = self._engine.d
            before = self._remotes.get()
            if before is None or (before.url, before.branch) != (remote.url, remote.branch):
                # A stop, a hold and "joined" are facts about one remote's
                # history; another remote starts from the join again.
                d.state.set_stop(None)
                d.state.set_confirmed(None)
                d.state.set_joined(False)
            self._remotes.put(remote)
            self._remotes.forget_removed()
            d.git.ensure()
            d.git.set_remote(remote.url, remote.username)
            d.git.set_carry_secret(remote.include_secret)

        await self._locked(apply)
        # A token supplied with the remote is approved with it; one already in
        # use elsewhere waits now. A token not stored here yet is reported by
        # the first round, with the ref it names.
        with contextlib.suppress(SecretMissing):
            await self._token.bind(remote, actor="user")
            await self._token.token_for(remote)
        return remote

    async def pause(self, enabled: bool) -> SyncRemote | None:
        current = await self.get_remote()
        if current is None:
            return None
        changed = dataclasses.replace(current, enabled=enabled)
        await asyncio.to_thread(self._remotes.put, changed)
        return changed

    async def clear_remote(self) -> bool:
        """Forget the remote. The vault and its history stay as they are.
        What was forgotten is kept (never a secret's value: the push secret is
        a name) so :meth:`restore_remote` can put it back."""

        def apply() -> bool:
            d = self._engine.d
            remote = self._remotes.get()
            if remote is None:
                return False
            stop = d.state.stop()
            confirmed = d.state.confirmed()
            self._remotes.keep_removed(
                {
                    "remote": remote.to_json(),
                    "joined": d.state.joined(),
                    "stop": to_json(stop) if stop is not None else None,
                    "join_choices": [to_json(c) for c in d.state.join_choices()],
                    "confirmed": list(confirmed) if confirmed else None,
                }
            )
            self._remotes.clear()
            d.git.clear_remote()
            d.git.set_carry_secret(False)
            d.state.set_stop(None)
            d.state.set_confirmed(None)
            d.state.set_join_choices([])
            d.state.set_joined(False)
            if d.scratch is not None:
                d.scratch.clear()
            return True

        done: bool = await self._locked(apply)
        return done

    async def restore_remote(self) -> SyncRemote:
        """Undo "Stop syncing": the remote that was forgotten, and what this
        machine knew about it (joined, a round waiting for a person, a join's
        differing files), as they were. Refused while another remote is set."""
        snapshot = await asyncio.to_thread(self._remotes.removed)
        if snapshot is None or not snapshot.get("remote"):
            raise SyncNothingToRestore("no remote was stopped on this machine")
        if await self.get_remote() is not None:
            raise SyncRemoteExists("a sync remote is set already; stop it before restoring one")
        remote = await self.set_remote(SyncRemote.from_json(snapshot["remote"]))

        def reinstate() -> None:
            d = self._engine.d
            d.state.set_joined(bool(snapshot.get("joined")))
            stop = snapshot.get("stop")
            d.state.set_stop(stop_from_json(stop) if stop else None)
            d.state.set_join_choices(
                [conflict_from_json(c) for c in snapshot.get("join_choices") or ()]
            )
            confirmed = snapshot.get("confirmed")
            d.state.set_confirmed((confirmed[0], confirmed[1]) if confirmed else None)

        await self._locked(reinstate)
        return remote

    async def check_remote(self, url: str, branch: str, secret_ref: str | None) -> RemoteCheck:
        """What the remote at ``url`` holds on ``branch``, without keeping it."""
        from coffer.application.sync.views import RemoteCheck

        candidate = SyncRemote(url=url, branch=branch, secret_ref=secret_ref)
        try:
            await self._token.bind(candidate, actor="user")
            token = await self._token.token_for(candidate)
        except SecretMissing as exc:
            return RemoteCheck("auth_failed", detail=str(exc))
        try:
            tip = await asyncio.to_thread(
                self._probe.probe, candidate.url, candidate.branch, token, candidate.username
            )
            if tip is None:
                return RemoteCheck("empty")
            layout = await asyncio.to_thread(
                self._probe.probe_layout, candidate.url, candidate.branch, token, candidate.username
            )
        except RemoteFailed as exc:
            result = {
                RemoteProblem.UNREACHABLE: "unreachable",
                RemoteProblem.AUTH_FAILED: "auth_failed",
            }.get(exc.problem, "failed")
            return RemoteCheck(result, detail=exc.detail)
        return RemoteCheck("vault" if layout is not None else "other", tip=tip, layout=layout)


__all__ = ["RemoteMixin"]
