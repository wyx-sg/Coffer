"""Per-agent local proxy tokens (ADR api-key-providers-are-reached-through-a-
separate-local-model-proxy; spec provider-switching "Authenticate each agent
to the proxy with its own local token").

Each managed agent gets its own random 256-bit token. It unlocks the loopback
model proxy and nothing else, and it tells the proxy which agent is calling —
which is how usage is attributed. It is kept in the credential store (as
Fernet ciphertext, like every secret) under ``proxy-token/<agent_uid>``, a
machine-local ref vault sync never carries, and handed out by
``coffer proxy token --agent-uid <uid>``, the command both agents run for it.

The token is not a boundary against a same-user process — anything that can
read the agent's config can run that command — and is kept for what it does
do: attribute usage, keep browser pages and other users' processes off the
user's quota, and fill the key field both agents insist on (ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, rule 5).
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Iterable
from typing import Protocol

from coffer.domain.model_proxy.state import PROXY_TOKEN_REF_PREFIX, token_digest

#: 32 random bytes — 256 bits.
_TOKEN_BYTES = 32


class _CredentialStore(Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


def token_ref(agent_uid: str) -> str:
    """The credential ref an agent's proxy token lives under."""
    return f"{PROXY_TOKEN_REF_PREFIX}{agent_uid}"


def new_token() -> str:
    """A fresh token; the ``cfr_`` prefix makes it recognisable in a log a
    user pastes, and different from every vendor's key shape."""
    return "cfr_" + secrets.token_urlsafe(_TOKEN_BYTES)


class ProxyTokenService:
    """Issues, reads, rotates and revokes agents' local proxy tokens."""

    def __init__(self, credentials: _CredentialStore) -> None:
        self._credentials = credentials
        # One agent, one token: two concurrent first reads must not mint two.
        self._lock = asyncio.Lock()

    async def token_for(self, agent_uid: str) -> str:
        """The agent's token, minted on first ask."""
        async with self._lock:
            ref = token_ref(agent_uid)
            existing = await asyncio.to_thread(self._credentials.get, ref)
            if existing:
                return existing
            token = new_token()
            await asyncio.to_thread(self._credentials.set, ref, token)
            return token

    async def rotate(self, agent_uid: str) -> str:
        """Replace the agent's token. The old one stops working at the next
        state push; both agents re-run their token command on their own
        cadence (Claude Code's helper cache is five minutes)."""
        async with self._lock:
            token = new_token()
            await asyncio.to_thread(self._credentials.set, token_ref(agent_uid), token)
            return token

    async def revoke(self, agent_uid: str) -> None:
        """Forget an agent's token (the agent was removed)."""
        async with self._lock:
            await asyncio.to_thread(self._credentials.delete, token_ref(agent_uid))

    async def digests(self, agent_uids: Iterable[str]) -> dict[str, str]:
        """``agent_uid -> sha256(token)`` for the proxy, minting as needed."""
        return {uid: token_digest(await self.token_for(uid)) for uid in agent_uids}


__all__ = ["ProxyTokenService", "new_token", "token_ref"]
