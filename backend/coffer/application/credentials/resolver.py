"""Materialise credential refs into actual secrets at use time.

Shared by every kind that stores credential refs in config (mcp_server
upstream spawn, channel adapters, the sync push). Secrets come from the
encrypted credential store. The materialised dict lives ONLY in the
consumer's process env / request headers / in-memory client. It is never
persisted, logged, or copied into any structured event payload.

A resolver built with a :class:`BoundaryPort` (every one the composition root
builds) resolves nothing without a destination: it first asks the boundary
whether each secret may go to that destination's target, and raises
``SecretBindingPending`` — injecting nothing — when a person has not approved
it yet (spec secret "Hold a secret for a new destination until a person
approves it").
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Protocol

from coffer.domain.errors import CredentialMissing
from coffer.domain.secrets import SecretDestination


class CredentialStorePort(Protocol):
    """Secret-store bridge (structural; the encrypted store wired at composition root)."""

    def get(self, ref: str) -> str | None: ...


class BoundaryPort(Protocol):
    """The approval gate (``application.credentials.boundary.SecretBoundary``)."""

    def require(self, dest: SecretDestination, refs: Mapping[str, str]) -> None: ...


class CredentialResolver:
    """Resolve credential refs against the credential store.

    Accepts any object satisfying :class:`CredentialStorePort`; the concrete
    adapter is wired at composition root.
    """

    def __init__(self, store: CredentialStorePort, boundary: BoundaryPort | None = None) -> None:
        self._store = store
        self._boundary = boundary

    def materialize(
        self, refs: dict[str, str], destination: SecretDestination | None = None
    ) -> dict[str, str]:
        """{key: credential_ref} -> {key: actual_secret}.

        Raises CredentialMissing if any ref isn't in the store, and
        SecretBindingPending if the boundary holds any of them for
        ``destination``. A boundary-guarded resolver refuses a call that names
        no destination: a consumer that cannot say where the secret goes may
        not have it.
        """
        if self._boundary is not None and refs:
            if destination is None:
                raise ValueError("a guarded credential resolver needs the secret's destination")
            self._boundary.require(destination, refs)
        out: dict[str, str] = {}
        for key, ref in refs.items():
            value = self._store.get(ref)
            if value is None:
                raise CredentialMissing(ref)
            out[key] = value
        return out

    async def materialize_async(
        self, refs: dict[str, str], destination: SecretDestination | None = None
    ) -> dict[str, str]:
        """:meth:`materialize`, run in a worker thread.

        The store read is a blocking SQLite call — on the event loop it would
        stall every concurrent request for as long as the read takes, and can
        deadlock against the coroutine holding the write lock. Every async
        consumer calls this one; nothing hand-rolls ``to_thread`` around
        :meth:`materialize` itself.
        """
        return await asyncio.to_thread(self.materialize, refs, destination)
