"""The remote's push token, resolved for the one round that needs it
(ADR credentials-across-machines; spec credentials "Hold a secret for a new
destination until a person approves it").

The remote names its token by ``credential_ref``; the value is materialised
through the secret boundary with the remote's URL as its destination, so an
existing token pointed at a URL it was never approved for waits for a person
in the desktop app rather than being sent there. The value is never stored on
the service and never written into the repository: git receives it through a
per-invocation credential helper.
"""

from __future__ import annotations

import asyncio

from coffer.application.credentials.resolver import CredentialResolver
from coffer.domain.secrets import sync_remote_destination
from coffer.domain.sync.remote import SyncRemote

_SLOT = "token"


class BoundaryToken:
    """Implements ``round_ports.TokenPort``."""

    def __init__(self, resolver: CredentialResolver) -> None:
        self._resolver = resolver

    async def token_for(self, remote: SyncRemote) -> str | None:
        if not remote.credential_ref:
            return None
        resolved = await asyncio.to_thread(
            self._resolver.materialize,
            {_SLOT: remote.credential_ref},
            sync_remote_destination(remote.url),
        )
        value = resolved.get(_SLOT)
        return str(value) if value is not None else None


__all__ = ["BoundaryToken"]
