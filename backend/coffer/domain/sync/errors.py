"""Sync error family (spec 010). Surfaces map these to HTTP status codes."""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.error_base import CofferError


class SyncNotConfigured(CofferError):  # noqa: N818
    """Sync has no remote configured / is disabled. Maps to 409."""

    code = "SYNC_NOT_CONFIGURED"

    def __init__(self, detail: str = "sync is not configured") -> None:
        super().__init__(detail)


class SyncInProgress(CofferError):  # noqa: N818
    """A sync run is already underway. Maps to 409."""

    code = "SYNC_IN_PROGRESS"

    def __init__(self) -> None:
        super().__init__("a sync run is already in progress")


class SyncConflict(CofferError):  # noqa: N818
    """A git merge left conflicting paths; the run imported nothing. Maps to 409."""

    code = "SYNC_CONFLICT"

    def __init__(self, paths: Sequence[str]) -> None:
        super().__init__(f"sync stopped on {len(paths)} conflicting path(s)")
        self.paths = list(paths)


class SyncWorkspaceTooNew(CofferError):  # noqa: N818
    """The workspace was written by a newer Coffer build. Maps to 409.

    Mirrors ``DB_SCHEMA_TOO_NEW``: refuse to import a layout this build does
    not understand instead of corrupting state.
    """

    code = "SYNC_WORKSPACE_TOO_NEW"

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"sync workspace schema version {found} is newer than this build "
            f"supports ({supported}); upgrade Coffer on this machine"
        )
        self.found = found
        self.supported = supported


class GitOperationFailed(CofferError):  # noqa: N818
    """A git subprocess returned non-zero for a non-conflict reason. Maps to 502."""

    code = "SYNC_GIT_FAILED"

    def __init__(self, operation: str, detail: str) -> None:
        super().__init__(f"git {operation} failed: {detail}")
        self.operation = operation
        self.detail = detail


class MasterKeyFileInvalid(CofferError):  # noqa: N818
    """A master-key file to import is missing or not a valid Fernet key. Maps to 422."""

    code = "MASTER_KEY_FILE_INVALID"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"master key file invalid ({reason}): {path}")
        self.path = path
        self.reason = reason


class SyncSerializationError(CofferError):
    """A workspace resource document is malformed on import. Maps to 422."""

    code = "SYNC_SERIALIZATION_INVALID"

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid sync document: {detail}")
        self.detail = detail
