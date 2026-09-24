"""KeyringAdapter — the only file in the codebase that imports `keyring`.

Secrets themselves live Fernet-encrypted in the coffer DB (see
encrypted_store.py); the OS keychain is used only for the opt-in
master-key storage (master_key.py) and as the read-side source when
migrating legacy pre-0.2 keychain entries into the encrypted store.

Importlinter contracts 3 and 4 forbid every other module from importing
`keyring`; only `coffer.infrastructure.credentials.*` is allowed.
"""

from __future__ import annotations

import contextlib

import keyring  # Credentials-invariant gatekeeper — the only import of keyring in the codebase
from keyring.errors import KeyringError, KeyringLocked, NoKeyringError

from coffer.domain.errors import CredentialLocked

_SERVICE = "coffer"


class KeyringAdapter:
    """Thin wrapper over `keyring` exposing only get / set / delete."""

    def get(self, ref: str) -> str | None:
        """The stored value, or None when there is none.

        A host with no keychain backend at all (``NoKeyringError``) holds
        nothing, so that is None too; a keychain that exists but cannot be
        read right now raises ``CredentialLocked`` — the caller must not read
        it as "absent" (``MasterKeyManager.resolve`` refuses to create a key
        over it)."""
        try:
            return keyring.get_password(_SERVICE, ref)
        except NoKeyringError:
            return None
        except KeyringLocked as e:
            raise CredentialLocked(f"keychain is locked: {e}") from e
        except KeyringError as e:
            raise CredentialLocked(f"keychain unavailable: {e}") from e

    def set(self, ref: str, value: str) -> None:
        try:
            keyring.set_password(_SERVICE, ref, value)
        except KeyringLocked as e:
            raise CredentialLocked(f"keychain is locked: {e}") from e

    def delete(self, ref: str) -> None:
        # Idempotent: delete-missing is fine, and adapters that don't
        # support delete (NullBackend) just no-op.
        with contextlib.suppress(KeyringLocked, KeyringError):
            keyring.delete_password(_SERVICE, ref)
