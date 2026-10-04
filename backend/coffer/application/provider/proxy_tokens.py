"""Per-agent local proxy tokens (ADR api-key-providers-are-reached-through-a-
separate-local-model-proxy; spec provider-switching "Authenticate each agent
to the proxy with its own local token").

Each managed agent gets its own random 256-bit token. It unlocks the loopback
model proxy and nothing else, and it tells the proxy which agent is calling —
which is how usage is attributed. It is kept in the secret store (as
Fernet ciphertext, like every secret) under ``proxy-token/<agent name>``
(``proxy-token/claude-code``) — an agent's name is fixed, so the ref reads as
whose token it is — a machine-local ref vault sync never carries, and handed
out by ``coffer proxy token --agent-uid <uid>``, the command both agents run
for it.

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


class _SecretStore(Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...
    def list_refs(self) -> list[tuple[str, str, str]]: ...


def token_ref(agent: str) -> str:
    """The secret ref an agent's proxy token lives under, by the agent's name."""
    return f"{PROXY_TOKEN_REF_PREFIX}{agent}"


def new_token() -> str:
    """A fresh token; the ``cfr_`` prefix makes it recognisable in a log a
    user pastes, and different from every vendor's key shape."""
    return "cfr_" + secrets.token_urlsafe(_TOKEN_BYTES)


class ProxyTokenService:
    """Issues, reads, rotates and revokes agents' local proxy tokens."""

    def __init__(self, secrets: _SecretStore) -> None:
        self._secrets = secrets
        # One agent, one token: two concurrent first reads must not mint two.
        self._lock = asyncio.Lock()

    async def token_for(self, agent: str) -> str:
        """The agent's token, minted on first ask."""
        return (await self.issue(agent))[0]

    async def issue(self, agent: str) -> tuple[str, bool]:
        """The agent's token, and whether this call minted it — the proxy needs
        a state push only then."""
        async with self._lock:
            ref = token_ref(agent)
            existing = await asyncio.to_thread(self._secrets.get, ref)
            if existing:
                return existing, False
            token = new_token()
            await asyncio.to_thread(self._secrets.set, ref, token)
            return token, True

    async def rotate(self, agent: str) -> str:
        """Replace the agent's token. The old one stops working at the next
        state push; both agents re-run their token command on their own
        cadence (Claude Code's helper cache is five minutes)."""
        async with self._lock:
            token = new_token()
            await asyncio.to_thread(self._secrets.set, token_ref(agent), token)
            return token

    async def revoke(self, agent: str) -> None:
        """Forget an agent's token (the agent was removed)."""
        async with self._lock:
            await asyncio.to_thread(self._secrets.delete, token_ref(agent))

    async def digests(self, agents: Iterable[str]) -> dict[str, str]:
        """``agent name -> sha256(token)`` for the proxy, minting as needed."""
        return {name: token_digest(await self.token_for(name)) for name in agents}

    async def prune(self, agents: Iterable[str]) -> list[str]:
        """Delete every proxy token whose agent is not one of ``agents`` (a
        removed agent's, or one stored under a key no agent goes by), and
        return the refs deleted. Such a token unlocks nothing: the proxy
        only knows the digests of current agents' tokens."""
        keep = {token_ref(name) for name in agents}
        async with self._lock:
            stale = [
                ref
                for ref, _c, _u in await asyncio.to_thread(self._secrets.list_refs)
                if ref.startswith(PROXY_TOKEN_REF_PREFIX) and ref not in keep
            ]
            for ref in stale:
                await asyncio.to_thread(self._secrets.delete, ref)
        return stale


__all__ = ["ProxyTokenService", "new_token", "token_ref"]
