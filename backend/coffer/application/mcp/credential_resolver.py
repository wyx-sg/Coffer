"""Materialise credential refs into actual secrets at upstream spawn time.

The materialised dict lives ONLY in the subprocess's env / the HTTP
request's headers. It is never persisted, logged, or copied into any
structured event payload.
"""

from __future__ import annotations

from coffer.application.mcp.ports import CredentialStorePort
from coffer.domain.errors import CredentialMissing


class CredentialResolver:
    """Resolve credential refs against the credential store.

    Accepts any object satisfying the :class:`CredentialStorePort` Protocol;
    the concrete adapter is wired at composition root (CODE-005).
    """

    def __init__(self, store: CredentialStorePort) -> None:
        self._store = store

    def materialize(self, refs: dict[str, str]) -> dict[str, str]:
        """{env_or_header: credential_ref} -> {env_or_header: actual_secret}.

        Raises CredentialMissing if any ref isn't in the store.
        """
        out: dict[str, str] = {}
        for key, ref in refs.items():
            value = self._store.get(ref)
            if value is None:
                raise CredentialMissing(ref)
            out[key] = value
        return out
