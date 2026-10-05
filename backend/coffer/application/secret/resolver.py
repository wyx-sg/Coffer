"""Materialise secret refs into actual secrets at use time.

Shared by every kind that stores secret refs in config (mcp_server
upstream spawn, channel adapters, the sync push). Secrets come from the
encrypted secret store. The materialised dict lives ONLY in the
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
from collections.abc import Callable, Mapping
from typing import Protocol

from coffer.domain.secret_errors import SecretMissing
from coffer.domain.secrets import SecretDestination


class SecretStorePort(Protocol):
    """Secret-store bridge (structural; the encrypted store wired at composition root)."""

    def get(self, ref: str) -> str | None: ...


class BoundaryPort(Protocol):
    """The approval gate (``application.secret.boundary.SecretBoundary``)."""

    def require(self, dest: SecretDestination, refs: Mapping[str, str]) -> None: ...

    def bind(self, dest: SecretDestination, refs: Mapping[str, str], *, actor: str) -> object: ...


#: ``(ref, destination, slot)`` — called once a value was decrypted for a
#: destination; the composition root audits it (spec secret "Audit every use of
#: a secret by who used it"). Never given a value.
UseListener = Callable[[str, SecretDestination, str], None]


class SecretResolver:
    """Resolve secret refs against the secret store.

    Accepts any object satisfying :class:`SecretStorePort`; the concrete
    adapter is wired at composition root.
    """

    def __init__(
        self,
        store: SecretStorePort,
        boundary: BoundaryPort | None = None,
        on_use: UseListener | None = None,
    ) -> None:
        self._store = store
        self._boundary = boundary
        self._on_use = on_use

    def materialize(
        self, refs: dict[str, str], destination: SecretDestination | None = None
    ) -> dict[str, str]:
        """{key: secret_ref} -> {key: actual_secret}.

        Raises SecretMissing if any ref isn't in the store, and
        SecretBindingPending if the boundary holds any of them for
        ``destination``. A boundary-guarded resolver refuses a call that names
        no destination: a consumer that cannot say where the secret goes may
        not have it.
        """
        if self._boundary is not None and refs:
            if destination is None:
                raise ValueError("a guarded secret resolver needs the secret's destination")
            self._boundary.require(destination, refs)
        out: dict[str, str] = {}
        for key, ref in refs.items():
            value = self._store.get(ref)
            if value is None:
                raise SecretMissing(ref)
            if destination is not None and self._on_use is not None:
                self._on_use(ref, destination, key)
            out[key] = value
        return out

    async def bind_async(
        self, refs: dict[str, str], destination: SecretDestination, *, actor: str
    ) -> None:
        """Evaluate a destination the moment a person registers or changes it:
        the value supplied for it is approved with the registration, anything
        else records its pending approval now (spec secret "Approve a secret's
        binding when its destination is registered"). Nothing is resolved."""
        if self._boundary is not None and refs:
            await asyncio.to_thread(self._boundary.bind, destination, refs, actor=actor)

    async def materialize_async(
        self, refs: dict[str, str], destination: SecretDestination | None = None
    ) -> dict[str, str]:
        """:meth:`materialize`, run in a worker thread.

        The store read is blocking file IO — on the event loop it would
        stall every concurrent request for as long as the read takes. Every async
        consumer calls this one; nothing hand-rolls ``to_thread`` around
        :meth:`materialize` itself.
        """
        return await asyncio.to_thread(self.materialize, refs, destination)
