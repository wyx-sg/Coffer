"""Materialise credential refs into actual secrets at upstream spawn time.

The materialised dict lives ONLY in the subprocess's env / the HTTP
request's headers. It is never persisted, logged, or copied into any
structured event payload.
"""

from __future__ import annotations

from coffer.application.mcp.ports import KeyringPort
from coffer.domain.errors import CredentialMissing


class CredentialResolver:
    """Resolve credential refs against the OS keychain.

    Accepts any object satisfying the :class:`KeyringPort` Protocol; the
    concrete adapter is wired at composition root (CODE-005).
    """

    def __init__(self, keyring: KeyringPort) -> None:
        self._keyring = keyring

    def materialize(self, refs: dict[str, str]) -> dict[str, str]:
        """{env_or_header: keychain_ref} -> {env_or_header: actual_secret}.

        Raises CredentialMissing if any ref isn't in the keychain.
        """
        out: dict[str, str] = {}
        for key, ref in refs.items():
            value = self._keyring.get(ref)
            if value is None:
                raise CredentialMissing(ref)
            out[key] = value
        return out
