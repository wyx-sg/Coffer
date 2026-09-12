"""Export/import error family (spec vault-export-import). Surfaces map these to HTTP codes."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class SyncBundleTooNew(CofferError):  # noqa: N818
    """The bundle was written by a newer Coffer build. Maps to 409.

    Mirrors ``DB_SCHEMA_TOO_NEW``: refuse to apply a layout this build does
    not understand instead of importing a partially-understood snapshot.
    """

    code = "SYNC_BUNDLE_TOO_NEW"

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"bundle schema version {found} is newer than this build "
            f"supports ({supported}); upgrade Coffer on this machine"
        )
        self.found = found
        self.supported = supported


class SyncBundleInvalid(CofferError):  # noqa: N818
    """The path given is not a readable export bundle. Maps to 422."""

    code = "SYNC_BUNDLE_INVALID"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"not a usable export bundle ({reason}): {path}")
        self.path = path
        self.reason = reason


class SyncSerializationError(CofferError):
    """A bundle document is malformed. Maps to 422."""

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
    """The backup remote's configuration cannot be used as given. Maps to 422."""

    code = "BACKUP_REMOTE_INVALID"

    def __init__(self, reason: str) -> None:
        super().__init__(f"backup remote invalid: {reason}")
        self.reason = reason
