"""Vault-sync errors a surface maps to an HTTP status (spec vault-sync).

Each is an ordinary state of the feature a person can act on — no remote yet,
a round or a machine that is not there, this machine asked to retire itself —
never a fault, so none of them may fall through to a 500.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class MasterKeyFileInvalid(CofferError):  # noqa: N818
    """Key material to import is missing or not a valid Fernet key. Maps to 422."""

    code = "MASTER_KEY_FILE_INVALID"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"master key file invalid ({reason}): {path}")
        self.path = path
        self.reason = reason


class SyncNoRemote(CofferError):  # noqa: N818
    """Nothing to sync with: no remote is configured. Maps to 409."""

    code = "SYNC_NO_REMOTE"

    def __init__(self) -> None:
        super().__init__("no sync remote is configured; set one first")


class SyncRoundNotFound(CofferError):  # noqa: N818
    """No recorded round has this id. Maps to 404."""

    code = "SYNC_ROUND_NOT_FOUND"

    def __init__(self, round_id: int) -> None:
        super().__init__(f"no sync round {round_id} is recorded on this machine")
        self.round_id = round_id


class SyncNoPlaintextFound(CofferError):  # noqa: N818
    """ "Push anyway" when the last round found no plaintext secret. Maps to 409."""

    code = "SYNC_NO_PLAINTEXT_FOUND"

    def __init__(self) -> None:
        super().__init__("the last round found no plaintext secret to push anyway")


class SyncMachineNotFound(CofferError):  # noqa: N818
    """No descriptor in the vault names this machine. Maps to 404."""

    code = "SYNC_MACHINE_NOT_FOUND"

    def __init__(self, machine_id: str) -> None:
        super().__init__(f"no machine {machine_id} is in the vault")
        self.machine_id = machine_id


class SyncMachineNameInvalid(CofferError):  # noqa: N818
    """A machine label that is empty or too long. Maps to 422."""

    code = "SYNC_MACHINE_NAME_INVALID"


class CannotRetireSelf(CofferError):  # noqa: N818
    """Retiring the machine you are standing on. Maps to 422."""

    code = "SYNC_CANNOT_RETIRE_SELF"

    def __init__(self, machine_id: str) -> None:
        super().__init__(
            f"{machine_id} is this machine; retire it from another machine, or "
            "clear the sync remote here instead"
        )


class MasterKeyPassphraseWrong(CofferError):  # noqa: N818
    """A protected key file did not open with the passphrase given. Maps to 422.

    Also the answer when no passphrase was given for a file that needs one:
    the two are the same situation to the person holding the file.
    """

    code = "MASTER_KEY_PASSPHRASE_WRONG"

    def __init__(self) -> None:
        super().__init__("the passphrase does not open this key file")


class MasterKeyPassphraseTooShort(CofferError):  # noqa: N818
    """A key backup was asked for with a passphrase under the minimum. Maps to 422."""

    code = "MASTER_KEY_PASSPHRASE_TOO_SHORT"

    def __init__(self, minimum: int) -> None:
        super().__init__(f"the passphrase must be at least {minimum} characters")
        self.minimum = minimum


__all__ = [
    "CannotRetireSelf",
    "MasterKeyFileInvalid",
    "MasterKeyPassphraseTooShort",
    "MasterKeyPassphraseWrong",
    "SyncMachineNameInvalid",
    "SyncMachineNotFound",
    "SyncNoPlaintextFound",
    "SyncNoRemote",
    "SyncRoundNotFound",
]
