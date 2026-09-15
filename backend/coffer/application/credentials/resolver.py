"""Materialise credential refs into actual secrets at use time.

Shared by every kind that stores credential refs in config (mcp_server
upstream spawn, channel adapters). Secrets come from the encrypted
credential store. The materialised dict lives ONLY in the
consumer's process env / request headers / in-memory client. It is never
persisted, logged, or copied into any structured event payload.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from coffer.domain.errors import CredentialMissing


class CredentialStorePort(Protocol):
    """Secret-store bridge (structural; the encrypted store wired at composition root)."""

    def get(self, ref: str) -> str | None: ...


class CredentialResolver:
    """Resolve credential refs against the credential store.

    Accepts any object satisfying :class:`CredentialStorePort`; the concrete
    adapter is wired at composition root (CODE-005).
    """

    def __init__(self, store: CredentialStorePort) -> None:
        self._store = store

    def materialize(self, refs: dict[str, str]) -> dict[str, str]:
        """{key: credential_ref} -> {key: actual_secret}.

        Raises CredentialMissing if any ref isn't in the store.
        """
        out: dict[str, str] = {}
        for key, ref in refs.items():
            value = self._store.get(ref)
            if value is None:
                raise CredentialMissing(ref)
            out[key] = value
        return out

    async def materialize_async(self, refs: dict[str, str]) -> dict[str, str]:
        """:meth:`materialize`, run in a worker thread.

        The store read is a blocking SQLite call (or the OS keychain in legacy
        setups); on the event loop it would stall every concurrent request for
        as long as the read takes. Async consumers call this one.
        """
        return await asyncio.to_thread(self.materialize, refs)
