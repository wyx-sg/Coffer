"""Credential-store error family; surfaces map codes to HTTP statuses."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class CredentialMissing(CofferError):  # noqa: N818
    code = "CREDENTIAL_MISSING"

    def __init__(self, ref: str) -> None:
        super().__init__(f"credential not found in the credential store: {ref}")
        self.ref = ref


class CredentialInUse(CofferError):  # noqa: N818
    """A credential cannot be deleted while a resource config still references it.

    Carries the human-readable refs of the citing resources (e.g.
    ``channel:my-bot``, ``mcp_server:github``) so the surface can tell the user
    which resources to detach before the credential can be removed.
    """

    code = "CREDENTIAL_IN_USE"

    def __init__(self, ref: str, references: list[str]) -> None:
        joined = ", ".join(references)
        super().__init__(
            f"credential {ref!r} is referenced by: {joined}; "
            "detach or delete those resources before deleting the credential"
        )
        self.ref = ref
        self.references = references


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
