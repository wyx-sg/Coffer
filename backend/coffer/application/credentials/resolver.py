"""Materialise credential refs into actual secrets at use time.

Shared by every kind that stores credential refs in config (mcp_server
upstream spawn, channel adapters). The materialised dict lives ONLY in the
consumer's process env / request headers / in-memory client. It is never
persisted, logged, or copied into any structured event payload.
"""

from __future__ import annotations

from typing import Protocol

from coffer.domain.errors import CredentialMissing


class KeyringPort(Protocol):
    """OS-keychain bridge (structural; adapter wired at composition root)."""

    def get(self, ref: str) -> str | None: ...


class CredentialResolver:
    """Resolve credential refs against the OS keychain.

    Accepts any object satisfying :class:`KeyringPort`; the concrete adapter
    is wired at composition root (CODE-005).
    """

    def __init__(self, keyring: KeyringPort) -> None:
        self._keyring = keyring

    def materialize(self, refs: dict[str, str]) -> dict[str, str]:
        """{key: keychain_ref} -> {key: actual_secret}.

        Raises CredentialMissing if any ref isn't in the keychain.
        """
        out: dict[str, str] = {}
        for key, ref in refs.items():
            value = self._keyring.get(ref)
            if value is None:
                raise CredentialMissing(ref)
            out[key] = value
        return out
