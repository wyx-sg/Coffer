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

from coffer.domain.errors import CredentialMissing
from coffer.domain.sync.remote import DEFAULT_USERNAME, SyncRemote
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
            d.git.ensure()
            d.git.set_remote(remote.url, remote.username)
            d.git.set_carry_secret(remote.include_secret)

        await self._locked(apply)
        # A token not stored here yet is reported by the first round, with the
        # ref it names.
        with contextlib.suppress(CredentialMissing):
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
        """Forget the remote. The vault and its history stay as they are."""

        def apply() -> bool:
            d = self._engine.d
            if self._remotes.get() is None:
                return False
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

    async def check_remote(
        self, url: str, branch: str, credential_ref: str | None, username: str = DEFAULT_USERNAME
    ) -> RemoteCheck:
        """What the remote at ``url`` holds on ``branch``, without keeping it."""
        from coffer.application.sync.views import RemoteCheck

        candidate = SyncRemote(
            url=url, branch=branch, credential_ref=credential_ref, username=username
        )
        try:
            token = await self._token.token_for(candidate)
        except CredentialMissing as exc:
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
