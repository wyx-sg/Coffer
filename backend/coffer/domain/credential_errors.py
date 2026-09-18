"""Credential-store error family; surfaces map codes to HTTP statuses."""

from __future__ import annotations

from coffer.domain.error_base import CofferError
from coffer.domain.resource import Resource


class CredentialMissing(CofferError):  # noqa: N818
    code = "CREDENTIAL_MISSING"

    def __init__(self, ref: str) -> None:
        super().__init__(f"credential not found in the credential store: {ref}")
        self.ref = ref


class CredentialInUse(CofferError):  # noqa: N818
    """A credential cannot be deleted while a resource config still references it.

    Built from the citing resources themselves, not from identifiers. The
    refusal is only useful if the user can act on it, and acting means finding
    the thing that still cites the credential — so the message says what each
    one is and what it is called: ``channel 'my-bot'``, ``mcp_server 'github'``.

    It deliberately does NOT name uids. A uid is the identity the system holds
    onto across a rename (ADR resource-identity-is-an-immutable-uid); it is not
    what the user sees on the page they have to go to next, and a refusal
    spelling out two opaque hex strings would be a worse answer than one
    spelling out two names.
    """

    code = "CREDENTIAL_IN_USE"

    def __init__(self, ref: str, citations: list[Resource]) -> None:
        # The label as it stands right now, read off the row at refusal time.
        # Nothing stores this string; it is composed for this one message.
        self.references = [f"{r.kind} {r.name!r}" for r in citations]
        joined = ", ".join(self.references)
        super().__init__(
            f"credential {ref!r} is still used by: {joined}; "
            "detach or delete those resources before deleting the credential"
        )
        self.ref = ref
        self.citations = citations


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
