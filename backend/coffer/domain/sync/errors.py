"""Vault-sync error family (spec vault-sync). Surfaces map these to HTTP codes."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class SyncBundleTooNew(CofferError):  # noqa: N818
    """The remote's tree was written by a newer Coffer build. Maps to 409.

    Mirrors ``DB_SCHEMA_TOO_NEW``: refuse a layout this build does not
    understand rather than half-applying it — and rather than publishing over
    it, which is the worse half on a remote the user's other machines share.
    Raised by ``domain.sync.manifest.refuse_if_too_new``.
    """

    code = "SYNC_BUNDLE_TOO_NEW"

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"the sync remote's layout version {found} is newer than this build "
            f"supports ({supported}); upgrade Coffer on this machine"
        )
        self.found = found
        self.supported = supported


class SyncBundleInvalid(CofferError):  # noqa: N818
    """The working tree cannot hold the vault's layout. Maps to 422.

    Raised while serializing, not while reading someone's archive: the tree
    the vault converges through is the "bundle" now, and this is a directory
    in it that is not a directory, or a root that is a file.
    """

    code = "SYNC_BUNDLE_INVALID"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"not a usable sync working tree ({reason}): {path}")
        self.path = path
        self.reason = reason


class SyncSerializationError(CofferError):
    """A document in the working tree is malformed. Maps to 422."""

    code = "SYNC_SERIALIZATION_INVALID"

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid bundle document: {detail}")
        self.detail = detail


class MasterKeyFileInvalid(CofferError):  # noqa: N818
    """A master-key file to import is missing or not a valid Fernet key. Maps to 422."""

    code = "MASTER_KEY_FILE_INVALID"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"master key file invalid ({reason}): {path}")
        self.path = path
        self.reason = reason


class BackupRemoteInvalid(CofferError):  # noqa: N818
    """The sync remote's configuration cannot be used as given. Maps to 422.

    The code and message keep the ``backup`` wording: both are wire contract
    and the surfaces already match on them."""

    code = "BACKUP_REMOTE_INVALID"

    def __init__(self, reason: str) -> None:
        super().__init__(f"backup remote invalid: {reason}")
        self.reason = reason


class SyncJoinAmbiguous(CofferError):  # noqa: N818
    """A returning machine whose base cannot be recovered. Maps to 409.

    Its descriptor is in the remote's registry, so this machine has converged
    before — but the commit it reached is gone (history rewritten, or the
    descriptor predates the field). Neither default is safe to pick silently:
    joining as new republishes everything the other machines deleted while this
    one was away, and rebuilding from the remote discards whatever this vault
    has that the remote does not. So the user chooses.
    """

    code = "SYNC_JOIN_AMBIGUOUS"

    def __init__(self, machine_id: str) -> None:
        super().__init__(
            f"this machine ({machine_id}) has synced with this remote before, but the "
            "commit it reached is no longer in the remote's history, so its base cannot "
            "be recovered. Re-run the join choosing either to keep this vault's own "
            "documents or to rebuild this machine from the remote."
        )
        self.machine_id = machine_id
