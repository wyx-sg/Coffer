"""Secret-store error family; surfaces map codes to HTTP statuses."""

from __future__ import annotations

from coffer.domain.error_base import CofferError
from coffer.domain.resource import Resource


class SecretMissing(CofferError):  # noqa: N818
    code = "SECRET_MISSING"

    def __init__(self, ref: str) -> None:
        super().__init__(f"secret not found in the secret store: {ref}")
        self.ref = ref


class SecretInUse(CofferError):  # noqa: N818
    """A secret cannot be deleted while a resource config still references it.

    Built from the citing resources themselves, not from identifiers. The
    refusal is only useful if the user can act on it, and acting means finding
    the thing that still cites the secret — so the message says what each
    one is and what it is called: ``channel 'my-bot'``, ``mcp_server 'github'``.

    It deliberately does NOT name uids. A uid is the identity the system holds
    onto across a rename (ADR identity-is-the-uid-inside-the-file); it is not
    what the user sees on the page they have to go to next, and a refusal
    spelling out two opaque hex strings would be a worse answer than one
    spelling out two names.
    """

    code = "SECRET_IN_USE"

    def __init__(self, ref: str, citations: list[Resource]) -> None:
        # The label as it stands right now, read off the row at refusal time.
        # Nothing stores this string; it is composed for this one message.
        self.references = [f"{r.kind} {r.name!r}" for r in citations]
        joined = ", ".join(self.references)
        super().__init__(
            f"secret {ref!r} is still used by: {joined}; "
            "detach or delete those resources before deleting the secret"
        )
        self.ref = ref
        self.citations = citations


class SecretLocked(CofferError):  # noqa: N818
    code = "SECRET_LOCKED"


class SecretUnreadable(CofferError):  # noqa: N818
    """A stored secret ciphertext could not be decrypted with the master key."""

    code = "SECRET_UNREADABLE"

    def __init__(self, ref: str) -> None:
        super().__init__(f"secret {ref!r} cannot be decrypted with the current master key")
        self.ref = ref


class MasterKeyMissing(CofferError):  # noqa: N818
    """Encrypted secrets exist but no master key was found in file or keychain."""

    code = "MASTER_KEY_MISSING"

    def __init__(self, key_path: str) -> None:
        super().__init__(
            f"secrets exist but master key was not found at {key_path} or in the OS keychain; "
            "restore the key file or re-enter your secrets"
        )
        self.key_path = key_path


class SecretBindingPending(CofferError):  # noqa: N818
    """A secret would go to a destination a person has not approved yet.

    Nothing is injected. The approval waits in the desktop app (ADR
    only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, rule 2); the
    ids name the waiting approvals so a surface can point at them.
    """

    code = "SECRET_BINDING_PENDING"

    def __init__(self, approval_ids: list[str], descriptions: list[str]) -> None:
        joined = "; ".join(descriptions)
        super().__init__(
            f"waiting for approval in the Coffer app: {joined}. Nothing was sent; "
            "open the Coffer desktop app to approve or reject (a rejected one stays "
            "refused until the destination changes)"
        )
        self.approval_ids = approval_ids


class SecretBindingRejected(SecretBindingPending):
    """A person refused this secret for this destination, and it stays refused.

    A kind of ``SecretBindingPending`` for every caller that only needs "the
    secret is withheld", but with its own code: nothing waits in the desktop
    app, so retrying or waiting changes nothing. The refusal holds until the
    destination changes.
    """

    code = "SECRET_BINDING_REJECTED"

    def __init__(self, approval_ids: list[str], descriptions: list[str]) -> None:
        joined = "; ".join(descriptions)
        CofferError.__init__(
            self,
            f"refused in the Coffer app: {joined}. Nothing was sent, and nothing waits; "
            "it stays refused until the destination changes",
        )
        self.approval_ids = approval_ids


class PresenceGrantInvalid(CofferError):  # noqa: N818
    """A presence grant that is missing, expired, reused or not signed by the app."""

    code = "PRESENCE_GRANT_INVALID"


class ApprovalNotFound(CofferError):  # noqa: N818
    code = "APPROVAL_NOT_FOUND"

    def __init__(self, approval_id: str) -> None:
        super().__init__(f"no approval {approval_id!r}")
        self.approval_id = approval_id


class ApprovalNotPending(CofferError):  # noqa: N818
    code = "APPROVAL_NOT_PENDING"

    def __init__(self, approval_id: str, status: str) -> None:
        super().__init__(f"approval {approval_id!r} is already {status}")
        self.approval_id = approval_id


class SecretNameInvalid(CofferError):  # noqa: N818
    code = "SECRET_NAME_INVALID"

    def __init__(self, name: str) -> None:
        super().__init__(
            f"invalid secret name {name!r}: one segment of [A-Za-z0-9_.-], at most 64 characters"
        )
        self.name = name


class SecretNotFound(CofferError):  # noqa: N818
    code = "SECRET_NOT_FOUND"

    def __init__(self, name: str) -> None:
        super().__init__(f"no standalone secret named {name!r} (coffer://secret/{name})")
        self.name = name
