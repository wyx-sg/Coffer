"""Credential-store error family; surfaces map codes to HTTP statuses."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class CredentialMissing(CofferError):  # noqa: N818
    code = "CREDENTIAL_MISSING"

    def __init__(self, ref: str) -> None:
        super().__init__(f"credential not found in the credential store: {ref}")
        self.ref = ref


class CredentialLocked(CofferError):  # noqa: N818
    code = "CREDENTIAL_LOCKED"


class CredentialUnreadable(CofferError):  # noqa: N818
    """A stored credential ciphertext could not be decrypted with the master key."""

    code = "CREDENTIAL_UNREADABLE"

    def __init__(self, ref: str) -> None:
        super().__init__(f"credential {ref!r} cannot be decrypted with the current master key")
        self.ref = ref


class MasterKeyMissing(CofferError):  # noqa: N818
    """Encrypted credentials exist but no master key was found in file or keychain."""

    code = "MASTER_KEY_MISSING"

    def __init__(self, key_path: str) -> None:
        super().__init__(
            f"credentials exist but master key was not found at {key_path} or in the OS keychain; "
            "restore the key file or re-enter your secrets"
        )
        self.key_path = key_path
